"""Invoice import service - main orchestration logic.

This module coordinates the invoice import process by:
1. Validating invoice data from JSON
2. Processing validated invoices (entity creation, position parsing)
3. Persisting invoices to the database
4. Updating publication payment statuses

This is the main entry point of the invoice_import package and is
exported as `import_invoices` from the package's public API.

The actual validation, parsing, entity creation, and payment update logic
is organized into separate private modules within this package.
"""

import json
from collections.abc import Iterable
from typing import BinaryIO, TextIO

from django.db import transaction

from coda.apps.contracts import repository as contract_repository
from coda.apps.invoices import creditor_repository, repository
from coda.contexts.finance.dto.import_dtos import ContractPositionImportDto, InvoiceImportDto
from coda.domain.contract import Contract
from coda.domain.finance.funding_sources import FundingSource
from coda.domain.finance.invoice import Invoice, InvoiceId, UnassignedCosts
from coda.domain.finance.invoice_positions import Position

from ._entity_creation import build_contract_lookup, build_publication_lookup
from ._funding_sources import stage_funding_sources
from ._parsing import build_invoice, parse_positions
from ._payment_updates import update_publication_payment_statuses
from ._validation import (
    build_missing_institution_errors,
    build_missing_publication_errors,
    find_invoices_with_missing_institutions,
    find_invoices_with_missing_publications,
    validate_invoices,
)
from .types import (
    ImportLookups,
    InvoiceImportDataError,
    InvoiceImportFailure,
    InvoiceImportPlan,
    InvoiceImportReport,
    InvoiceOutcome,
    InvoiceProcessingError,
    ParsedInvoice,
)

UNASSIGNED_COSTS_REASON = "Cannot import paid invoice with unassigned costs"


def import_invoices(json_stream: TextIO | BinaryIO) -> InvoiceImportReport:
    """Import invoices from JSON stream.

    Args:
        json_stream: JSON input containing invoice data

    Returns:
        Import report with counts and any processing errors

    Raises:
        InvoiceImportDataError: if the input is not valid JSON, the root is not a JSON
            object, or the ``invoices`` field is missing or not a list
    """
    text_content = json_stream.read()
    try:
        data = json.loads(text_content)
    except json.JSONDecodeError as exc:
        raise InvoiceImportDataError(
            [f"Invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"]
        ) from exc

    if not isinstance(data, dict):
        raise InvoiceImportDataError(["Import file must contain a JSON object"])

    if "invoices" not in data:
        raise InvoiceImportDataError(["invoices: Field required"])

    json_invoices = data["invoices"]
    if not isinstance(json_invoices, list):
        raise InvoiceImportDataError(["invoices: Input should be a valid list"])

    invoice_dtos, validation_errors = validate_invoices(json_invoices)
    processed_invoices, processing_errors = _process_invoices(invoice_dtos)
    all_errors = validation_errors + processing_errors

    return InvoiceImportReport(
        valid_invoices=len(processed_invoices),
        invalid_invoices=len({error.invoice_number for error in all_errors}),
        errors=all_errors,
    )


def _process_invoices(
    invoice_dtos: list[InvoiceImportDto],
) -> tuple[list[Invoice], list[InvoiceProcessingError]]:
    plan = _plan_invoices(invoice_dtos)
    errors = plan.errors()
    if not plan.invoices:
        return [], errors

    return _commit_invoices(plan), errors


def _plan_invoices(invoice_dtos: list[InvoiceImportDto]) -> InvoiceImportPlan:
    """Run prefilter → parse → domain validation, collecting failures per invoice."""
    candidates, prefilter_failures = _prefilter(invoice_dtos)
    lookups = _build_entity_lookups(candidates)

    parsed, parse_failures = _partition(
        [_parse_invoice(invoice_dto, lookups) for invoice_dto in candidates]
    )
    invoices, validation_failures = _partition([_validate_invoice(invoice) for invoice in parsed])

    return InvoiceImportPlan(
        invoices=tuple(invoices),
        lookups=lookups,
        failures=tuple(prefilter_failures + parse_failures + validation_failures),
    )


def _prefilter(
    invoice_dtos: list[InvoiceImportDto],
) -> tuple[list[InvoiceImportDto], list[InvoiceImportFailure]]:
    invoices_with_missing_publications = find_invoices_with_missing_publications(invoice_dtos)
    invoices_with_missing_institutions = find_invoices_with_missing_institutions(invoice_dtos)
    excluded_numbers = invoices_with_missing_publications | invoices_with_missing_institutions

    errors = build_missing_publication_errors(
        invoice_dtos, invoices_with_missing_publications
    ) + build_missing_institution_errors(invoice_dtos, invoices_with_missing_institutions)

    errors_by_number: dict[str, list[InvoiceProcessingError]] = {}
    for error in errors:
        errors_by_number.setdefault(error.invoice_number, []).append(error)

    candidates = [
        invoice_dto for invoice_dto in invoice_dtos if invoice_dto.number not in excluded_numbers
    ]
    failures = [
        InvoiceImportFailure(invoice_dto.number, tuple(errors_by_number[invoice_dto.number]))
        for invoice_dto in invoice_dtos
        if invoice_dto.number in excluded_numbers
    ]

    return candidates, failures


def _parse_invoice(invoice_dto: InvoiceImportDto, lookups: ImportLookups) -> InvoiceOutcome:
    results = parse_positions(invoice_dto, lookups)
    if results.has_errors():
        return InvoiceImportFailure(invoice_dto.number, tuple(results.errors()))

    return ParsedInvoice(invoice_dto, tuple(results.values()))


def _validate_invoice(invoice: ParsedInvoice) -> InvoiceOutcome:
    try:
        Invoice.ensure_all_costs_assigned(invoice.invoice_dto.status, invoice.positions)
    except UnassignedCosts:
        invoice_number = invoice.invoice_dto.number
        return InvoiceImportFailure(
            invoice_number,
            (InvoiceProcessingError(invoice_number, [UNASSIGNED_COSTS_REASON]),),
        )

    return invoice


def _partition(
    outcomes: Iterable[InvoiceOutcome],
) -> tuple[list[ParsedInvoice], list[InvoiceImportFailure]]:
    outcomes = list(outcomes)
    invoices = [outcome for outcome in outcomes if isinstance(outcome, ParsedInvoice)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, InvoiceImportFailure)]
    return invoices, failures


@transaction.atomic
def _commit_invoices(plan: InvoiceImportPlan) -> list[Invoice]:
    """Persist entities referenced by validated invoices, then the invoices."""
    validated_invoices = plan.invoices

    creditor_lookup = creditor_repository.get_or_create_creditors(
        invoice.invoice_dto.creditor for invoice in validated_invoices
    )
    plan.lookups.funding_sources.commit(
        source
        for invoice in validated_invoices
        for source in _referenced_funding_sources(invoice.positions)
    )
    _commit_contracts(plan.lookups.contract_lookup, _referenced_contract_names(validated_invoices))

    invoices = [
        build_invoice(
            invoice.invoice_dto,
            creditor_lookup[invoice.invoice_dto.creditor],
            invoice.positions,
        )
        for invoice in validated_invoices
    ]
    invoice_ids = repository.create_many(invoices)
    _assign_invoice_ids(invoices, invoice_ids)
    update_publication_payment_statuses(invoices)

    return invoices


def _referenced_funding_sources(positions: Iterable[Position]) -> Iterable[FundingSource]:
    return (
        funding.funding_source
        for position in positions
        for funding in position.funding_assignments()
        if funding.funding_source is not None
    )


def _commit_contracts(contract_lookup: dict[str, Contract], names: Iterable[str]) -> None:
    pending_names = sorted({name for name in names if contract_lookup[name].id is None})
    if not pending_names:
        return

    created = contract_repository.create_many(contract_lookup[name] for name in pending_names)
    created_by_name = {str(contract.name): contract for contract in created}
    for name in pending_names:
        contract_lookup[name].id = created_by_name[name].id


def _referenced_contract_names(invoices: Iterable[ParsedInvoice]) -> Iterable[str]:
    return (
        position.contract_name
        for invoice in invoices
        for position in invoice.invoice_dto.positions
        if isinstance(position, ContractPositionImportDto)
    )


def _assign_invoice_ids(invoices: list[Invoice], invoice_ids: list[InvoiceId]) -> None:
    for invoice, invoice_id in zip(invoices, invoice_ids):
        invoice.id = invoice_id


def _build_entity_lookups(invoice_dtos: list[InvoiceImportDto]) -> ImportLookups:
    """Build read-only and staged entity lookups; nothing is persisted here."""
    return ImportLookups(
        funding_sources=stage_funding_sources(invoice_dtos),
        request_id_lookup=build_publication_lookup(invoice_dtos),
        contract_lookup=build_contract_lookup(invoice_dtos),
    )

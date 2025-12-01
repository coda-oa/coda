import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, BinaryIO, TextIO, cast

import pydantic
from django.db.models import Q

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.institutions.models import Institution
from coda.apps.invoices import funding_source_repository, repository
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.apps.publications.services import publications
from coda.contexts.finance.dto.import_dtos import (
    CommonPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
    InvoiceImportDto,
    PublicationPositionImportDto,
)
from coda.domain import errors
from coda.domain.author import InstitutionId
from coda.domain.contract import Contract
from coda.domain.finance import invoice_positions
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import (
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
)
from coda.domain.finance.invoice_positions import (
    ContractItem,
    FreeItem,
    Position,
    PublicationItem,
)
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.payment import InvoiceReceived, PaymentEvent, PublicationPaid
from coda.domain.publication.publication import PublicationId
from coda.domain.string import NonEmptyStr


class InvoiceProcessingError(errors.DomainError):
    def __init__(self, invoice_number: str, reasons: list[str]) -> None:
        super().__init__()
        self.invoice_number = invoice_number
        self.reasons = reasons or []

    def unpack(self) -> tuple[str, list[str]]:
        return self.invoice_number, self.reasons


@dataclass
class InvoiceImportReport:
    valid_invoices: int
    invalid_invoices: int
    errors: list[InvoiceProcessingError]

    def invoices_with_errors(self) -> list[str]:
        return [err.invoice_number for err in self.errors]


@dataclass
class RelatedEntityLookups:
    creditor_lookup: dict[str, CreditorId]
    funding_sources_lookup: dict[str, FundingSourceId]
    request_id_lookup: dict[str, PublicationId]
    contract_lookup: dict[str, Contract]
    funding_assignments_lookup: dict[str, FundingSource]


def import_invoices(json_stream: TextIO | BinaryIO) -> InvoiceImportReport:
    text_content = json_stream.read()
    data = json.loads(text_content)

    invoice_dtos, validation_errors = _validate_invoices(data["invoices"])

    if validation_errors:
        return InvoiceImportReport(
            valid_invoices=0,
            invalid_invoices=len(validation_errors),
            errors=validation_errors,
        )

    processed_invoices, processing_errors = _process_invoices(invoice_dtos)

    return InvoiceImportReport(
        valid_invoices=len(processed_invoices),
        invalid_invoices=len(invoice_dtos) - len(processed_invoices),
        errors=processing_errors,
    )


def _validate_invoice(invoice_number: str, raw_invoice: dict[str, Any]) -> InvoiceImportDto:
    try:
        return InvoiceImportDto.model_validate(raw_invoice)
    except (ValueError, AttributeError) as e:
        raise InvoiceProcessingError(invoice_number, _format_validation_error(e))


def _validate_invoices(
    raw_invoices: list[dict[str, Any]],
) -> tuple[list[InvoiceImportDto], list[InvoiceProcessingError]]:
    """
    Validate a list of raw invoice data and return valid DTOs and validation errors.

    Returns:
        Tuple of (valid_invoice_dtos, validation_errors_by_invoice_number)
    """
    invoice_numbers = _extract_invoice_numbers(raw_invoices)

    with errors.capture(InvoiceProcessingError) as capture:
        parsed = errors.results(
            capture(_validate_invoice, invoice_numbers[i], raw_invoice)
            for i, raw_invoice in enumerate(raw_invoices)
        )

    invoice_dtos, errors_ = parsed.split()
    return invoice_dtos, errors_


def _extract_invoice_numbers(raw_invoices: list[dict[str, Any]]) -> list[str]:
    """Extract invoice numbers from raw JSON data, providing fallbacks for missing numbers."""
    return [
        raw_invoice.get("number", f"<unknown-{i}>") for i, raw_invoice in enumerate(raw_invoices)
    ]


def _format_validation_error(error: Exception) -> list[str]:
    """Format validation errors into a consistent list of string messages."""
    if isinstance(error, pydantic.ValidationError):
        return [str(err) for err in error.errors()]
    else:
        # Handle other validation-related exceptions
        return [str(error)]


def _process_invoices(
    invoice_dtos: list[InvoiceImportDto],
) -> tuple[list[Invoice], list[InvoiceProcessingError]]:
    """
    Process validated invoice DTOs into domain objects and persist them.

    Returns:
        Tuple of (created_invoices, processing_errors_by_invoice_number)
    """
    request_id_lookup, invoices_with_missing_publications = _find_publication_ids(invoice_dtos)

    valid_invoice_dtos = [
        invoice_dto
        for invoice_dto in invoice_dtos
        if invoice_dto.number not in invoices_with_missing_publications
    ]

    if not valid_invoice_dtos:
        return [], _build_missing_publication_errors(
            invoice_dtos, invoices_with_missing_publications
        )

    lookups = _build_entity_lookups(valid_invoice_dtos, request_id_lookup)
    invoices, invoice_processing_errors = _create_invoices(valid_invoice_dtos, lookups)

    invoice_ids = repository.bulk_create(invoices)
    _assign_invoice_ids(invoices, invoice_ids)
    _update_publication_payment_statuses(invoices)

    publication_processing_errors = _build_missing_publication_errors(
        invoice_dtos, invoices_with_missing_publications
    )

    return invoices, invoice_processing_errors + publication_processing_errors


def _assign_invoice_ids(invoices: list[Invoice], invoice_ids: list[InvoiceId]) -> None:
    for invoice, invoice_id in zip(invoices, invoice_ids):
        invoice.id = invoice_id


def _build_entity_lookups(
    invoice_dtos: list[InvoiceImportDto], request_id_lookup: dict[str, PublicationId]
) -> RelatedEntityLookups:
    """Build all necessary entity lookups for invoice processing."""
    return RelatedEntityLookups(
        creditor_lookup=_bulk_create_creditors(_creditors(invoice_dtos)),
        funding_sources_lookup=_bulk_create_funding_sources(_funding_sources(invoice_dtos)),
        request_id_lookup=request_id_lookup,
        contract_lookup=_find_contracts(_contracts(invoice_dtos)),
        funding_assignments_lookup=_build_funding_assignments_lookup(invoice_dtos),
    )


def _create_invoices(
    invoice_dtos: list[InvoiceImportDto], lookups: RelatedEntityLookups
) -> tuple[list[Invoice], list[InvoiceProcessingError]]:
    """Create domain invoice objects from DTOs and lookups."""
    positions_lookup = _build_positions_lookup(invoice_dtos, lookups)
    invoices_with_errors = [
        err
        for results in positions_lookup.values()
        for err in results.errors()
        if results.has_errors()
    ]
    valid_invoice_positions = {
        invoice_key: results.values()
        for invoice_key, results in positions_lookup.items()
        if not results.has_errors()
    }

    parsed_invoices = [
        _new_invoice(
            invoice_dto,
            lookups.creditor_lookup[invoice_dto.creditor],
            valid_invoice_positions[_invoice_key(invoice_dto)],
        )
        for invoice_dto in invoice_dtos
        if _invoice_key(invoice_dto) in valid_invoice_positions
    ]

    return parsed_invoices, invoices_with_errors


def _build_missing_publication_errors(
    all_invoice_dtos: list[InvoiceImportDto], invoices_with_missing_publications: set[str]
) -> list[InvoiceProcessingError]:
    """Build error dictionary for invoices with missing publications."""
    return [
        InvoiceProcessingError(
            invoice_dto.number, ["Invoice contains position with non-existing publication"]
        )
        for invoice_dto in all_invoice_dtos
        if invoice_dto.number in invoices_with_missing_publications
    ]


def _creditors(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (invoice_dto.creditor for invoice_dto in invoice_dtos if invoice_dto.creditor)


def _contracts(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (
        position.contract_name
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        if isinstance(position, ContractPositionImportDto)
    )


def _funding_sources(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (
        position.funding_source
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
    )


def _funding_assignment_sources(
    invoice_dtos: Iterable[InvoiceImportDto],
) -> Iterable[tuple[str, str]]:
    return (
        (fa.type, fa.name)
        for invoice in invoice_dtos
        for position in invoice.positions
        for fa in position.funding_assignments
    )


def _build_funding_assignments_lookup(
    invoice_dtos: list[InvoiceImportDto],
) -> dict[str, FundingSource]:
    """Build lookup of funding sources for split assignments, creating them if needed.

    Skips institutions that don't exist - these will cause KeyError during position parsing.
    """
    # Collect all unique (type, name) pairs
    unique_assignments = set(_funding_assignment_sources(invoice_dtos))
    if not unique_assignments:
        return {}

    # Separate budgets and institutions
    budgets = [name for type_, name in unique_assignments if type_ == "budget"]
    institutions_names = [name for type_, name in unique_assignments if type_ == "institution"]

    # Build domain objects for creation
    funding_sources_to_create: list[FundingSource] = []
    lookup_keys: list[str] = []

    # Add budgets
    for name in budgets:
        funding_sources_to_create.append(Budget.new(name))
        lookup_keys.append(name)

    # Add institutions (need to fetch institution IDs first)
    if institutions_names:
        institutions = {
            inst.name: InstitutionId(inst.pk)
            for inst in Institution.objects.filter(name__in=institutions_names)
        }
        for name in institutions_names:
            if name in institutions:
                funding_sources_to_create.append(SplitSource.new(institutions[name], name))
                lookup_keys.append(name)
            # If institution doesn't exist, skip it - will cause KeyError during parsing

    # Bulk create funding sources
    if not funding_sources_to_create:
        return {}

    funding_source_ids = funding_source_repository.create_many(funding_sources_to_create)

    # Assign IDs back to domain objects
    for funding_source, funding_source_id in zip(funding_sources_to_create, funding_source_ids):
        funding_source.id = funding_source_id

    # Return lookup by name
    return {name: fs for name, fs in zip(lookup_keys, funding_sources_to_create)}


def _build_positions_lookup(
    invoice_dtos: list[InvoiceImportDto], lookups: RelatedEntityLookups
) -> dict[str, errors.ResultCollection[Position, InvoiceProcessingError]]:
    def to_processing_error(
        ex: ValueError,
        invoice_dto: InvoiceImportDto,
    ) -> InvoiceProcessingError:
        return InvoiceProcessingError(invoice_dto.number, [str(ex)])

    with errors.capture(ValueError) as capture:
        return {
            _invoice_key(invoice_dto): errors.results(
                capture(
                    _parse_into_position, p, Currency.from_code(invoice_dto.currency), lookups
                ).map_err(to_processing_error, invoice_dto)
                for p in invoice_dto.positions
            )
            for invoice_dto in invoice_dtos
        }


def _parse_into_position(
    p: CommonPositionImportDto, currency: Currency, lookups: RelatedEntityLookups
) -> Position:
    cost = Money(p.amount, currency)
    tax_rate = TaxRate.from_percentage(p.tax_rate)
    funding_source_id = (
        lookups.funding_sources_lookup[p.funding_source] if p.funding_source else None
    )
    external_id = p.external_id
    position: Position
    match p:
        case PublicationPositionImportDto():
            id_type = cast(str, p.request_id or p.legacy_request_id)
            position = invoice_positions.create(
                item=PublicationItem(
                    lookups.request_id_lookup[id_type],
                    cost_type=p.cost_type,
                ),
                cost=cost,
                tax_rate=tax_rate,
                external_position_id=external_id,
            )
        case ContractPositionImportDto():
            position = invoice_positions.create(
                item=ContractItem(
                    lookups.contract_lookup[p.contract_name].in_year(p.contract_year),
                    cost_type=p.cost_type,
                ),
                cost=cost,
                tax_rate=tax_rate,
                external_position_id=external_id,
            )
        case FreePositionImportDto():
            position = invoice_positions.create(
                item=FreeItem(
                    p.description,
                    cost_type=p.cost_type,
                ),
                cost=cost,
                tax_rate=tax_rate,
                external_position_id=external_id,
            )
        case _:
            raise ValueError(f"Unknown position type: {p.type}.\n{p}")

    if p.funding_source:
        position.assign_remaining(Budget(funding_source_id, p.funding_source))
    else:
        implicit_assignments = [fa for fa in p.funding_assignments if fa.amount is None]
        partial_assignment = Decimal(0)
        if implicit_assignments:
            total_explicit = sum(fa.amount for fa in p.funding_assignments if fa.amount is not None)
            remaining = p.amount - total_explicit
            partial_assignment = remaining / Decimal(len(implicit_assignments))

        for fa in p.funding_assignments:
            try:
                funding_source = lookups.funding_assignments_lookup[fa.name]
            except KeyError:
                # Institution doesn't exist - raise error that will be caught
                raise ValueError(f"Institution '{fa.name}' does not exist")
            assignment_amount = fa.amount if fa.amount is not None else partial_assignment
            position.assign_funding(funding_source, assignment_amount)

    return position


def _invoice_key(invoice_dto: InvoiceImportDto) -> str:
    return str(hash(invoice_dto.model_dump_json()))


def _new_invoice(
    invoice_dto: InvoiceImportDto,
    creditor: CreditorId,
    positions: list[Position],
) -> Invoice:
    invoice = Invoice.new(
        number=invoice_dto.number,
        date=invoice_dto.date,
        creditor=creditor,
        status=invoice_dto.status,
        external_invoice_id=invoice_dto.external_id,
        comment=invoice_dto.comment,
        positions=positions,
    )

    if invoice_dto.conversion:
        invoice.add_conversion(
            invoice_dto.conversion.exchange_rate,
            Currency.from_code(invoice_dto.conversion.target_currency),
        )

    return invoice


def _find_publication_ids(
    invoices: Iterable[InvoiceImportDto],
) -> tuple[dict[str, PublicationId], set[str]]:
    invoices_with_publications = [
        (invoice_dto.number, cast(str, position.request_id or position.legacy_request_id))
        for invoice_dto in invoices
        for position in invoice_dto.positions
        if isinstance(position, PublicationPositionImportDto)
    ]

    publication_ids = {publication for _, publication in invoices_with_publications}

    requests = FundingRequest.objects.filter(
        Q(request_id__in=publication_ids) | Q(legacy_request_id__in=publication_ids)
    ).prefetch_related("publication")

    found_publication_ids = set()
    for req in requests:
        found_publication_ids.add(req.request_id)
        if req.legacy_request_id:
            found_publication_ids.add(req.legacy_request_id)

    invoices_with_missing_publications = {
        invoice_number
        for invoice_number, publication in invoices_with_publications
        if publication not in found_publication_ids
    }

    return {req.request_id: PublicationId(req.publication.id) for req in requests} | {
        req.legacy_request_id: PublicationId(req.publication.id)
        for req in requests
        if req.legacy_request_id
    }, invoices_with_missing_publications


def _find_contracts(contracts: Iterable[str]) -> dict[str, Contract]:
    contracts = set(contracts)
    existing = contract_repository.find_all_by_names(contracts)
    existing_map: dict[str, Contract] = {c.name: c for c in existing}
    to_create = [
        Contract.new(name=NonEmptyStr(name)) for name in contracts if name not in existing_map
    ]
    if to_create:
        created = contract_repository.create_many(to_create)
        existing_map.update({c.name: c for c in created})
    return {name: existing_map[name] for name in contracts}


def _bulk_create_creditors(creditors: Iterable[str]) -> dict[str, CreditorId]:
    creditors = set(creditors)
    existing = Creditor.objects.filter(name__in=creditors)
    existing_map = {c.name: c for c in existing}
    to_create = [Creditor(name=name) for name in creditors if name not in existing_map]
    if to_create:
        created = Creditor.objects.bulk_create(to_create)
        existing_map.update({c.name: c for c in created})
    return {name: CreditorId(existing_map[name].pk) for name in creditors}


def _bulk_create_funding_sources(funding_sources: Iterable[str]) -> dict[str, FundingSourceId]:
    funding_sources = set(funding_sources)
    existing = FundingSourceModel.objects.filter(name__in=funding_sources)
    existing_map = {fs.name: FundingSourceId(fs.pk) for fs in existing}
    to_create = [
        FundingSourceModel(name=name) for name in funding_sources if name not in existing_map
    ]
    if to_create:
        created = FundingSourceModel.objects.bulk_create(to_create)
        existing_map.update({fs.name: FundingSourceId(fs.pk) for fs in created})

    return existing_map


def _update_publication_payment_statuses(invoices: list[Invoice]) -> None:
    """
    Update funding request payment statuses based on imported invoice payment statuses.
    This uses bulk operations for optimal performance during large imports.
    """
    payment_updates = [
        (publication_id, _create_payment(invoice))
        for invoice in invoices
        for publication_id in _publication_positions(invoice)
        if invoice.id
    ]

    if payment_updates:
        publications.bulk_update_payments(payment_updates)


def _publication_positions(invoice: Invoice) -> list[PublicationId]:
    return [p.item.item for p in invoice.positions if isinstance(p.item.item, PublicationId)]


def _create_payment(invoice: Invoice) -> PaymentEvent:
    if not invoice.id:
        raise ValueError("Invoice must have an ID to create a payment status.")

    if invoice.is_paid():
        return PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)

    return InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)

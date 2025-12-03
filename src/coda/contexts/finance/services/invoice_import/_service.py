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
from typing import BinaryIO, TextIO

from coda.apps.invoices import repository
from coda.contexts.finance.dto.import_dtos import InvoiceImportDto
from coda.domain import errors
from coda.domain.finance.invoice import Invoice, InvoiceId
from coda.domain.finance.invoice_positions import Position
from coda.domain.money._currency import Currency
from coda.domain.publication.publication import PublicationId

from ._entity_creation import (
    build_funding_assignments_lookup,
    bulk_create_creditors,
    bulk_create_funding_sources,
    find_contracts,
)
from ._parsing import (
    create_invoice,
    invoice_key,
    parse_into_position,
)
from ._payment_updates import (
    update_publication_payment_statuses,
)
from ._validation import (
    build_missing_institution_errors,
    build_missing_publication_errors,
    find_invoices_with_missing_institutions,
    find_publication_ids,
    validate_invoices,
)
from .types import (
    ImportLookups,
    InvoiceImportReport,
    InvoiceProcessingError,
)


def import_invoices(json_stream: TextIO | BinaryIO) -> InvoiceImportReport:
    """Import invoices from JSON stream.

    Args:
        json_stream: JSON input containing invoice data

    Returns:
        Import report with counts and any processing errors
    """
    text_content = json_stream.read()
    data = json.loads(text_content)

    invoice_dtos, validation_errors = validate_invoices(data["invoices"])

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


def _process_invoices(
    invoice_dtos: list[InvoiceImportDto],
) -> tuple[list[Invoice], list[InvoiceProcessingError]]:
    """
    Process validated invoice DTOs into domain objects and persist them.

    Returns:
        Tuple of (created_invoices, processing_errors_by_invoice_number)
    """
    request_id_lookup, invoices_with_missing_publications = find_publication_ids(invoice_dtos)
    invoices_with_missing_institutions = find_invoices_with_missing_institutions(invoice_dtos)

    # Filter out invoices with missing publications OR missing institutions
    invalid_invoice_numbers = (
        invoices_with_missing_publications | invoices_with_missing_institutions
    )

    valid_invoice_dtos = [
        invoice_dto
        for invoice_dto in invoice_dtos
        if invoice_dto.number not in invalid_invoice_numbers
    ]

    if not valid_invoice_dtos:
        return [], (
            build_missing_publication_errors(invoice_dtos, invoices_with_missing_publications)
            + build_missing_institution_errors(invoice_dtos, invoices_with_missing_institutions)
        )

    lookups = _build_entity_lookups(valid_invoice_dtos, request_id_lookup)
    invoices, invoice_processing_errors = _create_invoices(valid_invoice_dtos, lookups)

    invoice_ids = repository.bulk_create(invoices)
    _assign_invoice_ids(invoices, invoice_ids)
    update_publication_payment_statuses(invoices)

    all_errors = (
        invoice_processing_errors
        + build_missing_publication_errors(invoice_dtos, invoices_with_missing_publications)
        + build_missing_institution_errors(invoice_dtos, invoices_with_missing_institutions)
    )

    return invoices, all_errors


def _assign_invoice_ids(invoices: list[Invoice], invoice_ids: list[InvoiceId]) -> None:
    for invoice, invoice_id in zip(invoices, invoice_ids):
        invoice.id = invoice_id


def _build_entity_lookups(
    invoice_dtos: list[InvoiceImportDto], request_id_lookup: dict[str, PublicationId]
) -> ImportLookups:
    """Build all necessary entity lookups for invoice processing."""
    return ImportLookups(
        creditor_lookup=bulk_create_creditors(invoice_dtos),
        funding_sources_lookup=bulk_create_funding_sources(invoice_dtos),
        request_id_lookup=request_id_lookup,
        contract_lookup=find_contracts(invoice_dtos),
        funding_assignments_lookup=build_funding_assignments_lookup(invoice_dtos),
    )


def _create_invoices(
    invoice_dtos: list[InvoiceImportDto], lookups: ImportLookups
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
        create_invoice(
            invoice_dto,
            lookups.creditor_lookup[invoice_dto.creditor],
            valid_invoice_positions[invoice_key(invoice_dto)],
        )
        for invoice_dto in invoice_dtos
        if invoice_key(invoice_dto) in valid_invoice_positions
    ]

    return parsed_invoices, invoices_with_errors


def _build_positions_lookup(
    invoice_dtos: list[InvoiceImportDto], lookups: ImportLookups
) -> dict[str, errors.ResultCollection[Position, InvoiceProcessingError]]:
    def to_processing_error(
        ex: ValueError,
        invoice_dto: InvoiceImportDto,
    ) -> InvoiceProcessingError:
        return InvoiceProcessingError(invoice_dto.number, [str(ex)])

    with errors.capture(ValueError) as capture:
        return {
            invoice_key(invoice_dto): errors.results(
                capture(
                    parse_into_position, p, Currency.from_code(invoice_dto.currency), lookups
                ).map_err(to_processing_error, invoice_dto)
                for p in invoice_dto.positions
            )
            for invoice_dto in invoice_dtos
        }

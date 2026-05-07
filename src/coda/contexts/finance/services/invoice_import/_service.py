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
from coda.domain.finance.invoice import Invoice
from coda.uow import UnitOfWork

from ._contract_import_repository import ContractImportRepository
from ._creditor_import_repository import CreditorImportRepository
from ._funding_source_import_repository import FundingSourceImportRepository
from ._parsing import create_invoices_from_dtos
from ._payment_updates import update_publication_payment_statuses
from ._publication_import_repository import PublicationImportRepository
from ._validation import (
    build_missing_institution_errors,
    build_missing_publication_errors,
    find_invoices_with_missing_institutions,
    find_invoices_with_missing_publications,
    validate_invoices,
)
from .types import InvoiceImportReport, InvoiceProcessingError


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
    invoices_with_missing_publications = find_invoices_with_missing_publications(invoice_dtos)
    invoices_with_missing_institutions = find_invoices_with_missing_institutions(invoice_dtos)

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

    publication_repo = PublicationImportRepository()
    publication_repo.prefetch(valid_invoice_dtos)

    contract_repo = ContractImportRepository()
    contract_repo.prefetch(valid_invoice_dtos)

    creditor_repo = CreditorImportRepository()
    creditor_repo.prefetch({dto.creditor for dto in valid_invoice_dtos if dto.creditor})

    funding_source_repo = FundingSourceImportRepository()
    funding_source_repo.prefetch_funding_sources(
        {p.funding_source for dto in valid_invoice_dtos for p in dto.positions if p.funding_source}
    )
    funding_source_repo.prefetch_institutions(
        {
            fa.name
            for dto in valid_invoice_dtos
            for p in dto.positions
            for fa in p.funding_assignments
            if fa.type == "institution"
        }
    )

    with UnitOfWork(creditor_repo, funding_source_repo, repository) as uow:
        invoices, invoice_processing_errors = create_invoices_from_dtos(
            valid_invoice_dtos,
            publication_repo,
            contract_repo,
            creditor_repo,
            funding_source_repo,
            uow,
        )
        for invoice in invoices:
            uow.register(invoice)

    update_publication_payment_statuses(invoices)

    all_errors = (
        invoice_processing_errors
        + build_missing_publication_errors(invoice_dtos, invoices_with_missing_publications)
        + build_missing_institution_errors(invoice_dtos, invoices_with_missing_institutions)
    )

    return invoices, all_errors

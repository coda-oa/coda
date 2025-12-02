"""Private module for validation logic during invoice import."""

from collections.abc import Iterable
from typing import Any, cast

import pydantic
from django.db.models import Q

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.institutions.models import Institution
from coda.contexts.finance.dto.import_dtos import (
    InvoiceImportDto,
    PublicationPositionImportDto,
)
from coda.contexts.finance.services.invoice_import.types import InvoiceProcessingError
from coda.domain import errors
from coda.domain.publication.publication import PublicationId


def validate_invoices(
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


def _validate_invoice(invoice_number: str, raw_invoice: dict[str, Any]) -> InvoiceImportDto:
    try:
        return InvoiceImportDto.model_validate(raw_invoice)
    except (ValueError, AttributeError) as e:
        raise InvoiceProcessingError(invoice_number, _format_validation_error(e))


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


def build_missing_publication_errors(
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


def build_missing_institution_errors(
    all_invoice_dtos: list[InvoiceImportDto], invoices_with_missing_institutions: set[str]
) -> list[InvoiceProcessingError]:
    """Build error dictionary for invoices with missing institutions."""
    return [
        InvoiceProcessingError(invoice_dto.number, ["Institution does not exist"])
        for invoice_dto in all_invoice_dtos
        if invoice_dto.number in invoices_with_missing_institutions
    ]


def find_invoices_with_missing_institutions(
    invoice_dtos: Iterable[InvoiceImportDto],
) -> set[str]:
    """
    Find invoices that reference non-existing institutions in funding assignments.

    Returns:
        Set of invoice numbers that reference missing institutions
    """
    # Collect all institution names referenced in funding assignments
    institution_names = {
        fa.name
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        for fa in position.funding_assignments
        if fa.type == "institution"
    }

    if not institution_names:
        return set()

    # Query which institutions exist
    existing_institutions = set(
        Institution.objects.filter(name__in=institution_names).values_list("name", flat=True)
    )

    # Find missing institutions
    missing_institutions = institution_names - existing_institutions

    if not missing_institutions:
        return set()

    # Find which invoices reference missing institutions
    invoices_with_missing = {
        invoice_dto.number
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        for fa in position.funding_assignments
        if fa.type == "institution" and fa.name in missing_institutions
    }

    return invoices_with_missing


def find_publication_ids(
    invoices: Iterable[InvoiceImportDto],
) -> tuple[dict[str, Any], set[str]]:
    """
    Find publications by request ID, returning both a lookup dict and error info.

    Returns:
        Tuple of (request_id_to_publication_id_lookup, invoice_numbers_with_missing_publications)
    """

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

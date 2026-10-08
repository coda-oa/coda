"""Invoice import service and manual invoice pipeline.

This module coordinates both the bulk import path (JSON invoices) and
the manual entry path (web form), sharing position construction and
payment-update logic through a single pipeline.
"""

import json
from typing import BinaryIO, TextIO

from coda.apps.invoices import repository
from coda.apps.publications.services import publications
from coda.contexts.finance.dto.edit_position_dtos import PositionDto
from coda.contexts.finance.dto.import_dtos import InvoiceImportDto
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.contexts.finance.services.invoice_import._payment_updates import (
    _invoice_received,
    _pay_publications,
    _publication_positions,
    _unpay_deleted_publication_positions,
    update_publication_payment_statuses,
    update_single_invoice_payments,
)
from coda.contexts.finance.services.invoice_import._position_parser import (
    InvoiceParseError,
    InvoiceTotal,
    PositionParseError,
    parse_invoice,
    position_to_dto,
    to_position,
)
from coda.domain.finance.invoice import Invoice, InvoiceId

from ._entity_creation import (
    build_contract_lookup,
    build_creditor_lookup,
    build_funding_assignments_lookup,
    build_funding_source_lookup,
    build_publication_lookup,
)
from ._parsing import create_invoices_from_dtos
from ._validation import (
    build_missing_institution_errors,
    build_missing_publication_errors,
    find_invoices_with_missing_institutions,
    find_invoices_with_missing_publications,
    validate_invoices,
)
from .types import ImportLookups, InvoiceImportReport, InvoiceProcessingError


# --- Bulk import path ---


def import_invoices(json_stream: TextIO | BinaryIO) -> InvoiceImportReport:
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

    lookups = _build_entity_lookups(valid_invoice_dtos)
    invoices, invoice_processing_errors = create_invoices_from_dtos(valid_invoice_dtos, lookups)

    invoice_ids = repository.create_many(invoices)
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


def _build_entity_lookups(invoice_dtos: list[InvoiceImportDto]) -> ImportLookups:
    return ImportLookups(
        creditor_lookup=build_creditor_lookup(invoice_dtos),
        funding_sources_lookup=build_funding_source_lookup(invoice_dtos),
        request_id_lookup=build_publication_lookup(invoice_dtos),
        contract_lookup=build_contract_lookup(invoice_dtos),
        funding_assignments_lookup=build_funding_assignments_lookup(invoice_dtos),
    )


# --- Manual entry path ---


def process_manual(invoice_head: InvoiceHeadDto, positions: list[PositionDto]) -> Invoice:
    return parse_invoice(invoice_head, positions)


# --- Shared persistence ---


def save(invoice: Invoice) -> InvoiceId:
    _unpay_deleted_publication_positions(invoice)

    if not invoice.id:
        invoice.id = repository.create(invoice)
    else:
        repository.update(invoice)

    update_single_invoice_payments(invoice)
    return invoice.id


def save_many(invoices: list[Invoice]) -> list[InvoiceId]:
    invoice_ids = repository.create_many(invoices)
    _assign_invoice_ids(invoices, invoice_ids)
    update_publication_payment_statuses(invoices)
    return invoice_ids


# --- Payment lifecycle actions ---


def pay_invoice(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    invoice.pay()
    repository.update(invoice)
    _pay_publications(invoice)


def reset_payment(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    invoice.reset_payment()
    repository.update(invoice)
    _invoice_received(invoice)


def delete_invoice(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    for p in _publication_positions(invoice):
        publications.invoice_deleted(p, invoice_id)

    repository.delete(invoice_id)

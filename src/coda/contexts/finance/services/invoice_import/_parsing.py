"""Parsing logic for converting import DTOs to domain objects.

This module handles the transformation of import DTOs into domain objects,
including position parsing and invoice construction.
Uses the shared to_position() from _position_parser.py.
"""

from functools import partial

from coda.contexts.finance.dto.import_dtos import (
    InvoiceImportDto,
)
from coda.contexts.finance.services.invoice_import._position_parser import to_position
from coda.contexts.finance.services.invoice_import.types import (
    ImportLookups,
    InvoiceProcessingError,
)
from coda.domain import errors
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import Position
from coda.domain.money import Currency


def create_invoice(
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


def invoice_key(invoice_dto: InvoiceImportDto) -> str:
    return str(hash(invoice_dto.model_dump_json()))


def build_positions_for_invoices(
    invoice_dtos: list[InvoiceImportDto], lookups: ImportLookups
) -> dict[str, errors.ResultCollection[Position, InvoiceProcessingError]]:
    def to_processing_error(
        ex: ValueError,
        invoice_dto: InvoiceImportDto,
    ) -> InvoiceProcessingError:
        return InvoiceProcessingError(invoice_dto.number, [str(ex)])

    import_parse = partial(to_position, lookups=lookups, parse_safe=False)

    positions = {}
    with errors.capture(ValueError) as capture:
        for invoice_dto in invoice_dtos:
            currency = Currency.from_code(invoice_dto.currency)

            positions[invoice_key(invoice_dto)] = errors.results(
                [
                    capture(import_parse, p, currency).map_err(to_processing_error, invoice_dto)
                    for p in invoice_dto.positions
                ]
            )

    return positions


def create_invoices_from_dtos(
    invoice_dtos: list[InvoiceImportDto], lookups: ImportLookups
) -> tuple[list[Invoice], list[InvoiceProcessingError]]:
    positions_lookup = build_positions_for_invoices(invoice_dtos, lookups)
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

"""Parsing logic for converting import DTOs to domain objects.

This module handles the transformation of import DTOs into domain objects,
including position parsing and invoice construction.
"""

from collections.abc import Iterable
from typing import cast

from coda.contexts.finance.dto.import_dtos import (
    ContractPositionImportDto,
    FreePositionImportDto,
    InvoiceImportDto,
    PositionImportDto,
    PublicationPositionImportDto,
)
from coda.contexts.finance.services.invoice_import.types import (
    ImportLookups,
    InvoiceProcessingError,
)
from coda.domain import errors
from coda.domain.finance import invoice_positions
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import (
    ContractItem,
    FreeItem,
    PartialAssignment,
    Position,
    PublicationItem,
)
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


def parse_into_position(
    p: PositionImportDto, currency: Currency, lookups: ImportLookups
) -> Position:
    """Parse import DTO into a domain Position object.

    Args:
        p: Position import DTO (Publication, Contract, or Free)
        currency: Currency for this position
        lookups: Entity lookups for references

    Returns:
        Domain Position object with funding assignments

    Raises:
        ValueError: If position type is unknown or data is invalid
    """
    cost = Money(p.amount, currency)
    tax_rate = TaxRate.from_percentage(p.tax_rate)
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
        position.assign_remaining(lookups.funding_sources.assignments[("budget", p.funding_source)])
    else:
        position.assign_many(
            [
                PartialAssignment(
                    lookups.funding_sources.assignments[(fa.type, fa.name)],
                    fa.amount,
                )
                for fa in p.funding_assignments
            ]
        )

    return position


def build_invoice(
    invoice_dto: InvoiceImportDto,
    creditor: CreditorId,
    positions: Iterable[Position],
) -> Invoice:
    """Build a domain Invoice from an already validated DTO and parsed positions."""
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


def _to_processing_error(ex: ValueError, invoice_dto: InvoiceImportDto) -> InvoiceProcessingError:
    return InvoiceProcessingError(invoice_dto.number, [str(ex)])


def parse_positions(
    invoice_dto: InvoiceImportDto, lookups: ImportLookups
) -> errors.ResultCollection[Position, InvoiceProcessingError]:
    """Parse all positions of one invoice, capturing per-position errors."""
    currency = Currency.from_code(invoice_dto.currency)
    with errors.capture(ValueError) as capture:
        return errors.results(
            [
                capture(parse_into_position, p, currency, lookups).map_err(
                    _to_processing_error, invoice_dto
                )
                for p in invoice_dto.positions
            ]
        )

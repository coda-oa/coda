"""Parsing logic for converting import DTOs to domain objects.

This module handles the transformation of import DTOs into domain objects,
including position parsing and invoice construction.
"""

from decimal import Decimal
from typing import cast

from coda.contexts.finance.dto.import_dtos import (
    CommonPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
    InvoiceImportDto,
    PublicationPositionImportDto,
)
from coda.contexts.finance.services.invoice_import.types import ImportLookups
from coda.domain.finance import invoice_positions
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import (
    ContractItem,
    FreeItem,
    Position,
    PublicationItem,
)
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


def parse_into_position(
    p: CommonPositionImportDto, currency: Currency, lookups: ImportLookups
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
            funding_source = lookups.funding_assignments_lookup[fa.name]
            assignment_amount = fa.amount if fa.amount is not None else partial_assignment
            position.assign_funding(funding_source, assignment_amount)

    return position


def create_invoice(
    invoice_dto: InvoiceImportDto,
    creditor: CreditorId,
    positions: list[Position],
) -> Invoice:
    """Create a domain Invoice object from import DTO.

    Args:
        invoice_dto: Invoice import DTO
        creditor: Creditor ID for this invoice
        positions: List of parsed position objects

    Returns:
        Domain Invoice object
    """
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
    """Generate a unique hash key for an invoice DTO.

    Used for grouping positions by invoice during processing.

    Args:
        invoice_dto: Invoice import DTO

    Returns:
        Hash string uniquely identifying this invoice
    """
    return str(hash(invoice_dto.model_dump_json()))

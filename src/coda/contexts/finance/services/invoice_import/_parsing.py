"""Parsing logic for converting import DTOs to domain objects.

This module handles the transformation of import DTOs into domain objects,
including position parsing and invoice construction.
"""

from typing import TYPE_CHECKING, cast

from coda.contexts.finance.dto.import_dtos import (
    ContractPositionImportDto,
    FreePositionImportDto,
    InvoiceImportDto,
    PositionImportDto,
    PublicationPositionImportDto,
)
from coda.contexts.finance.services.invoice_import.types import InvoiceProcessingError
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

if TYPE_CHECKING:
    from ._contract_import_repository import ContractImportRepository
    from ._creditor_import_repository import CreditorImportRepository
    from ._funding_source_import_repository import FundingSourceImportRepository
    from ._publication_import_repository import PublicationImportRepository
    from coda.uow import UnitOfWork


def parse_into_position(
    p: PositionImportDto,
    currency: Currency,
    publication_repo: "PublicationImportRepository",
    contract_repo: "ContractImportRepository",
    funding_source_repo: "FundingSourceImportRepository",
    uow: "UnitOfWork",
) -> Position:
    """Parse import DTO into a domain Position object.

    Args:
        p: Position import DTO (Publication, Contract, or Free)
        currency: Currency for this position
        publication_repo: Repository for resolving request IDs to PublicationIds
        contract_repo: Repository for resolving contract names to Contract objects
        funding_source_repo: Repository for resolving/staging funding sources
        uow: Unit of work for staging new funding sources

    Returns:
        Domain Position object with funding assignments

    Raises:
        ValueError: If position type is unknown or data is invalid
    """
    cost = Money(p.amount, currency)
    tax_rate = TaxRate.from_percentage(p.tax_rate)
    funding_source = (
        funding_source_repo.get_or_create(uow, p.funding_source) if p.funding_source else None
    )
    external_id = p.external_id
    position: Position
    match p:
        case PublicationPositionImportDto():
            id_type = cast(str, p.request_id or p.legacy_request_id)
            position = invoice_positions.create(
                item=PublicationItem(
                    publication_repo.get(id_type),
                    cost_type=p.cost_type,
                ),
                cost=cost,
                tax_rate=tax_rate,
                external_position_id=external_id,
            )
        case ContractPositionImportDto():
            position = invoice_positions.create(
                item=ContractItem(
                    contract_repo.get(p.contract_name).in_year(p.contract_year),
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

    if funding_source is not None:
        position.assign_remaining(funding_source)
        return position

    position.assign_many(
        [
            PartialAssignment(
                funding_source_repo.get_or_create_for_assignment(uow, fa.type, fa.name),
                fa.amount,
            )
            for fa in p.funding_assignments
        ]
    )

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


def create_invoices_from_dtos(
    invoice_dtos: list[InvoiceImportDto],
    publication_repo: "PublicationImportRepository",
    contract_repo: "ContractImportRepository",
    creditor_repo: "CreditorImportRepository",
    funding_source_repo: "FundingSourceImportRepository",
    uow: "UnitOfWork",
) -> tuple[list[Invoice], list[InvoiceProcessingError]]:
    """Create domain invoice objects from DTOs and repositories.

    Args:
        invoice_dtos: Invoice DTOs to transform
        publication_repo: Repository for resolving request IDs to PublicationIds
        contract_repo: Repository for resolving contract names to Contract objects
        creditor_repo: Repository for resolving/staging creditors
        funding_source_repo: Repository for resolving/staging funding sources
        uow: Unit of work for staging new entities

    Returns:
        Tuple of (created_invoices, processing_errors)
    """
    invoices: list[Invoice] = []
    processing_errors: list[InvoiceProcessingError] = []

    with errors.capture(ValueError) as capture:
        for invoice_dto in invoice_dtos:
            currency = Currency.from_code(invoice_dto.currency)

            # NOTE: important to use a list as an argument here!
            # generator would capture currency variable lazily resulting in all invoices having the same currency!
            position_results = errors.results(
                [
                    capture(
                        parse_into_position,
                        p,
                        currency,
                        publication_repo,
                        contract_repo,
                        funding_source_repo,
                        uow,
                    ).map_err(_into_processing_error, invoice_dto)
                    for p in invoice_dto.positions
                ]
            )

            if position_results.has_errors():
                processing_errors.extend(position_results.errors())
                continue

            invoices.append(
                create_invoice(
                    invoice_dto,
                    creditor_repo.get_or_create(uow, invoice_dto.creditor),
                    position_results.values(),
                )
            )

    return invoices, processing_errors


def _into_processing_error(ex: Exception, dto: InvoiceImportDto) -> InvoiceProcessingError:
    return InvoiceProcessingError(dto.number, [str(ex)])

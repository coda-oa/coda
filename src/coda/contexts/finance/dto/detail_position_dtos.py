from dataclasses import dataclass, field
from decimal import Decimal

from django.urls import reverse

from coda.contexts.finance.dto.edit_position_dtos import (
    ContractItemDto,
    FreeItemDto,
    PositionDto,
    PublicationItemDto,
)
from coda.contexts.finance.services import invoice_parser
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import Position


class UnsupportedPositionTypeError(Exception):
    """Raised when an unsupported position DTO type is encountered."""

    pass


DEFAULT_TAX_RATE_PERCENTAGE = 19


@dataclass
class FundingAssignmentDetailDto:
    """DTO for displaying funding assignment details in the invoice detail view."""

    funding_source_id: int | None
    funding_source_name: str
    amount: Decimal


@dataclass
class PositionDetailDto:
    type: str = ""
    title: str = ""
    url: str = ""
    funding_assignments: list[FundingAssignmentDetailDto] = field(default_factory=list)
    cost_type: str = PublicationCostType.Publication_Charge.value
    tax_rate: Decimal = Decimal(DEFAULT_TAX_RATE_PERCENTAGE)
    tax_amount: Decimal = Decimal("0.00")
    net_costs: Decimal = Decimal("0.00")

    @classmethod
    def to_position_detail_dto(cls, position: Position) -> "PositionDetailDto":
        return build_position_detail_dto(position)


def _build_funding_assignments(position: Position) -> list[FundingAssignmentDetailDto]:
    """
    Build funding assignment details with resolved funding source names.

    Note: Amounts are already in the correct currency because the position
    has been converted via invoice.convert(display_currency) before reaching this point.
    """

    assignments = position.funding_assignments()
    if not assignments:
        return []

    return [
        FundingAssignmentDetailDto(
            funding_source_id=fs.funding_source.id if fs.funding_source else None,
            funding_source_name=fs.funding_source.name if fs.funding_source else "unspecified",
            amount=fs.amount.amount,
        )
        for fs in assignments
    ]


def build_position_detail_dto(position: Position) -> PositionDetailDto:
    dto = invoice_parser.position_to_dto(position)

    match dto.item:
        case PublicationItemDto():
            return _from_publication_dto(dto, position)
        case ContractItemDto():
            return _from_contract_dto(dto, position)
        case FreeItemDto():
            return _from_free_dto(dto, position)


def _from_publication_dto(dto: PositionDto, position: Position) -> "PositionDetailDto":
    assert isinstance(dto.item, PublicationItemDto)
    return PositionDetailDto(
        type=dto.type,
        title=dto.item.title,
        url=dto.item.funding_request.url,
        funding_assignments=_build_funding_assignments(position),
        cost_type=dto.item.cost_type,
        tax_rate=dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )


def _from_contract_dto(dto: PositionDto, position: Position) -> "PositionDetailDto":
    assert isinstance(dto.item, ContractItemDto)
    url = reverse("contracts:detail", kwargs={"pk": dto.item.id})
    return PositionDetailDto(
        type=dto.type,
        title=dto.item.name,
        url=url,
        funding_assignments=_build_funding_assignments(position),
        cost_type=dto.item.cost_type,
        tax_rate=dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )


def _from_free_dto(dto: PositionDto, position: Position) -> "PositionDetailDto":
    assert isinstance(dto.item, FreeItemDto)
    return PositionDetailDto(
        type=dto.type,
        title=dto.item.description,
        url="",
        funding_assignments=_build_funding_assignments(position),
        cost_type=dto.item.cost_type,
        tax_rate=dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )

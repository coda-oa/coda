from dataclasses import dataclass, field
from decimal import Decimal

from django.urls import reverse

from coda.contexts.finance.dto.edit_position_dtos import (
    PositionDto,
    ContractItemDto,
    FreeItemDto,
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
    funding_source: int | None = None  # Legacy field, kept for backward compatibility
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
    from coda.apps.invoices.models import FundingSource as FundingSourceModel

    assignments = position.funding_assignments()
    if not assignments:
        return []

    # Collect funding source IDs to load in bulk
    from coda.domain.finance.funding_sources import Budget, SplitSource

    fs_ids = []
    for a in assignments:
        if a.funding_source:
            fs = a.funding_source
            # Use isinstance to narrow the union type for mypy
            if isinstance(fs, (Budget, SplitSource)) and fs.id:
                fs_ids.append(fs.id)

    # Load funding sources in bulk to avoid N+1 queries
    fs_lookup = {fs.pk: fs.name for fs in FundingSourceModel.objects.filter(id__in=fs_ids)}

    # Build DTOs with resolved names
    result = []
    for a in assignments:
        fs_id = None
        fs_name = "Unassigned"

        if a.funding_source:
            fs = a.funding_source
            # Use isinstance to narrow the union type for mypy
            if isinstance(fs, (Budget, SplitSource)):
                fs_id = fs.id
                fs_name = fs_lookup.get(fs_id, "Unknown") if fs_id else "Unknown"
            else:
                fs_name = "Unknown"

        result.append(
            FundingAssignmentDetailDto(
                funding_source_id=fs_id,
                funding_source_name=fs_name,
                amount=a.amount.amount,
            )
        )

    return result


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
        funding_source=dto.funding_source,
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
        funding_source=dto.funding_source,
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
        funding_source=dto.funding_source,
        funding_assignments=_build_funding_assignments(position),
        cost_type=dto.item.cost_type,
        tax_rate=dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )

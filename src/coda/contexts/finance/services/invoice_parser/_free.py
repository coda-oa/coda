from typing_extensions import TypeIs

from coda.contexts.finance.dto.edit_position_dtos import (
    FreePositionDto,
    FundingAssignmentDto,
    PositionDto,
)
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import FreeItem, Position, PositionItemType


def _parse_item(position: FreePositionDto, *, parse_safe: bool = True) -> str:
    _ = parse_safe
    return position.description


def _parse_cost_type(position: FreePositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def parse_item_from(position: FreePositionDto, *, parse_safe: bool = False) -> PositionItemType:
    return FreeItem(_parse_item(position, parse_safe=parse_safe), _parse_cost_type(position))


def position_to_dto(position: Position) -> FreePositionDto:
    assert _is_freeitem(position.item)
    return FreePositionDto(
        description=position.item.item,
        funding_source=position.funding_source,
        cost_amount=position.cost.amount,
        cost_type=position.item.cost_type.value,
        tax_rate=position.tax_rate.percentage(),
        external_position_id=position.external_position_id,
        funding_assignments=[
            FundingAssignmentDto(funding_source=f.funding_source, amount=f.amount.amount)
            for f in position.funding_assignments()
        ],
        unassigned_costs=position.unassigned_costs().amount,
    )


def _is_freeitem(item: PositionItemType) -> TypeIs[FreeItem]:
    return isinstance(item, FreeItem)


class FreeParser:
    def position_to_dto(self, position: Position) -> PositionDto:
        return position_to_dto(position)

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        assert isinstance(position, FreePositionDto)
        return parse_item_from(position, parse_safe=parse_safe)


parser = FreeParser()

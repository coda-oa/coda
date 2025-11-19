from typing_extensions import TypeIs

from coda.contexts.finance.dto.edit_position_dtos import FreeItemDto, ItemDto, PositionDto
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import FreeItem, Position, PositionItemType


def _parse_item(position: PositionDto, *, parse_safe: bool = True) -> str:
    assert isinstance(position.item, FreeItemDto)
    _ = parse_safe
    return position.item.description


def _parse_cost_type(position: PositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def parse_item_from(position: PositionDto, *, parse_safe: bool = False) -> PositionItemType:
    return FreeItem(_parse_item(position, parse_safe=parse_safe), _parse_cost_type(position))


def to_itemdto(position: Position) -> ItemDto:
    assert _is_freeitem(position.item)
    return FreeItemDto(description=position.item.item, cost_type=position.item.cost_type.value)


def _is_freeitem(item: PositionItemType) -> TypeIs[FreeItem]:
    return isinstance(item, FreeItem)


class FreeParser:
    def to_itemdto(self, position: Position) -> ItemDto:
        return to_itemdto(position)

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        return parse_item_from(position, parse_safe=parse_safe)


parser = FreeParser()

from typing_extensions import TypeIs

from coda.contexts.finance.dto.edit_position_dtos import FreeItemDto, ItemDto, PositionDto
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import FreeItem, Position, PositionItemType
from .types import PositionParser


class FreeParser(PositionParser):
    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        assert isinstance(position.item, FreeItemDto)
        return FreeItem(
            position.item.description,
            PublicationCostType(position.item.cost_type),
        )

    def to_itemdto(self, position: Position) -> ItemDto:
        assert _is_freeitem(position.item)
        return FreeItemDto(
            description=position.item.item,
            cost_type=position.item.cost_type.value,
        )


def _is_freeitem(item: PositionItemType) -> TypeIs[FreeItem]:
    return isinstance(item, FreeItem)


parser = FreeParser()

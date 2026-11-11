from typing_extensions import TypeIs

from coda.apps.contracts import repository
from coda.contexts.finance.dto.edit_position_dtos import ContractItemDto, ItemDto, PositionDto
from coda.domain.contract import ContractId
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.invoice_positions import ContractItem, Position, PositionItemType

from .types import PositionParser


class ContractParser(PositionParser):
    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        assert isinstance(position.item, ContractItemDto)
        contract = repository.get_by_id(ContractId(position.item.id))
        if not parse_safe:
            item = contract.in_year(position.item.year)
        else:
            item = contract.in_first_year()

        return ContractItem(item, ContractCostType(position.item.cost_type))

    def to_itemdto(self, position: Position) -> ItemDto:
        assert _is_contractitem(position.item)
        contract_year = position.item.item
        assert contract_year.id is not None
        return ContractItemDto(
            id=contract_year.id,
            name=contract_year.name,
            cost_type=position.item.cost_type.value,
            year=contract_year.year,
        )


def _is_contractitem(item: PositionItemType) -> TypeIs[ContractItem]:
    return isinstance(item, ContractItem)


parser = ContractParser()

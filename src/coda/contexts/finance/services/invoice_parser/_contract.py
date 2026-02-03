from typing import TypeIs

from coda.apps.contracts import repository
from coda.contexts.finance.dto.edit_position_dtos import ContractItemDto, ItemDto, PositionDto
from coda.domain.contract import ContractId, ContractYear
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.invoice_positions import ContractItem, Position, PositionItemType


def _parse_item(position: PositionDto, *, parse_safe: bool = False) -> ContractYear:
    assert isinstance(position.item, ContractItemDto)
    contract = repository.get_by_id(ContractId(position.item.id))
    if not parse_safe:
        item = contract.in_year(position.item.year)
    else:
        item = contract.in_first_year()

    return item


def _parse_cost_type(position: PositionDto) -> ContractCostType:
    return ContractCostType(position.item.cost_type)


def parse_item_from(position: PositionDto, *, parse_safe: bool = False) -> PositionItemType:
    return ContractItem(_parse_item(position, parse_safe=parse_safe), _parse_cost_type(position))


def to_itemdto(position: Position) -> ItemDto:
    assert _is_contractitem(position.item)
    if not position.item.item.contract_id:
        raise ValueError("Contract ID is required for ContractPosition")

    contract = repository.get_by_id(position.item.item.contract_id)
    assert contract.id is not None
    return ContractItemDto(
        id=contract.id,
        name=contract.name,
        cost_type=position.item.cost_type.value,
        year=position.item.item.year,
    )


def _is_contractitem(item: PositionItemType) -> TypeIs[ContractItem]:
    return isinstance(item, ContractItem)


class ContractParser:
    def to_itemdto(self, position: Position) -> ItemDto:
        return to_itemdto(position)

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        return parse_item_from(position, parse_safe=parse_safe)


parser = ContractParser()

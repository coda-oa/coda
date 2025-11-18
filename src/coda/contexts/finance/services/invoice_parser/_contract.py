from typing_extensions import TypeIs

from coda.apps.contracts import repository
from coda.contexts.finance.dto.edit_position_dtos import (
    ContractPositionDto,
    FundingAssignmentDto,
    PositionDto,
)
from coda.domain.contract import ContractId, ContractYear
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.invoice_positions import ContractItem, Position, PositionItemType


def _parse_item(position: ContractPositionDto, *, parse_safe: bool = False) -> ContractYear:
    contract = repository.get_by_id(ContractId(position.id))
    if not parse_safe:
        item = contract.in_year(position.year)
    else:
        item = contract.in_first_year()

    return item


def _parse_cost_type(position: ContractPositionDto) -> ContractCostType:
    return ContractCostType(position.cost_type)


def parse_item_from(position: ContractPositionDto, *, parse_safe: bool = False) -> PositionItemType:
    return ContractItem(_parse_item(position, parse_safe=parse_safe), _parse_cost_type(position))


def position_to_dto(position: Position) -> ContractPositionDto:
    assert _is_contractitem(position.item)
    if not position.item.item.contract_id:
        raise ValueError("Contract ID is required for ContractPosition")

    contract = repository.get_by_id(position.item.item.contract_id)

    assert contract.id is not None
    return ContractPositionDto(
        id=contract.id,
        name=contract.name,
        funding_source=position.funding_source,
        year=position.item.item.year,
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


def _is_contractitem(item: PositionItemType) -> TypeIs[ContractItem]:
    return isinstance(item, ContractItem)


class ContractParser:
    def position_to_dto(self, position: Position) -> PositionDto:
        assert _is_contractitem(position.item)
        return position_to_dto(position)

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        assert isinstance(position, ContractPositionDto)
        return parse_item_from(position, parse_safe=parse_safe)


parser = ContractParser()

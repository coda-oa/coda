from typing_extensions import TypeIs

from coda.apps.contracts import repository
from coda.contexts.finance.dto.edit_position_dtos import (
    PositionDto,
    ContractPositionDto,
    FundingAssignmentDto,
)
from coda.domain.contract import ContractId, ContractYear
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.invoice_positions import Position, ContractItem, PositionItemType
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


def parse_item(position: ContractPositionDto, *, parse_safe: bool = False) -> ContractYear:
    contract = repository.get_by_id(ContractId(position.id))
    if not parse_safe:
        item = contract.in_year(position.year)
    else:
        item = contract.in_first_year()

    return item


def parse_cost_type(position: ContractPositionDto) -> ContractCostType:
    return ContractCostType(position.cost_type)


def to_position(
    position: ContractPositionDto, currency: Currency, *, parse_safe: bool = False
) -> Position:
    item = parse_item(position, parse_safe=parse_safe)
    cost_type = parse_cost_type(position)

    _position = invoice_positions.create(
        item=ContractItem(item, cost_type=cost_type),
        cost=Money(position.cost_amount, currency),
        tax_rate=TaxRate.from_percentage(position.tax_rate),
        funding_source=FundingSourceId(position.funding_source)
        if position.funding_source
        else None,
        external_position_id=position.external_position_id,
    )

    for f in position.funding_assignments:
        fid = FundingSourceId(f.funding_source) if f.funding_source else None
        _position.assign_funding(fid, f.amount)

    return _position


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
    def to_position(
        self, position: PositionDto, currency: Currency, *, parse_safe: bool = False
    ) -> Position:
        assert isinstance(position, ContractPositionDto)
        return to_position(position, currency, parse_safe=parse_safe)

    def position_to_dto(self, position: Position) -> PositionDto:
        assert _is_contractitem(position.item)
        return position_to_dto(position)


parser = ContractParser()

from decimal import Decimal

from coda.apps.contracts import repository
from coda.contexts.finance.dto.edit_position_dtos import (
    AnyPositionDto,
    ContractPositionDto,
)
from coda.domain.contract import ContractId, ContractYear
from coda.domain.invoice import (
    AnyPosition,
    ContractCostType,
    ContractPosition,
    FundingSourceId,
    TaxRate,
)
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
) -> ContractPosition:
    item = parse_item(position, parse_safe=parse_safe)
    cost_type = parse_cost_type(position)

    return ContractPosition(
        item=item,
        cost_type=cost_type,
        cost=Money(position.cost_amount, currency),
        tax_rate=TaxRate.from_percentage(position.tax_rate),
        funding_source=FundingSourceId(position.funding_source)
        if position.funding_source
        else None,
        external_position_id=position.external_position_id,
    )


def position_to_dto(position: ContractPosition) -> ContractPositionDto:
    if not position.item.contract_id:
        raise ValueError("Contract ID is required for ContractPosition")

    contract = repository.get_by_id(position.item.contract_id)

    is_vat = position.cost_type == ContractCostType.Vat

    assert contract.id is not None
    return ContractPositionDto(
        id=contract.id,
        name=contract.name,
        funding_source=position.funding_source,
        year=position.item.year,
        cost_amount=position.cost.amount,
        cost_type=position.cost_type.value,
        tax_rate=Decimal("0.00") if is_vat else position.tax_rate.percentage(),
        external_position_id=position.external_position_id,
        tax_amount=position.tax().amount,
    )


class ContractParser:
    def to_position(
        self, position: AnyPositionDto, currency: Currency, *, parse_safe: bool = False
    ) -> AnyPosition:
        assert isinstance(position, ContractPositionDto)
        return to_position(position, currency, parse_safe=parse_safe)

    def position_to_dto(self, position: AnyPosition) -> AnyPositionDto:
        assert isinstance(position, ContractPosition)
        return position_to_dto(position)


parser = ContractParser()

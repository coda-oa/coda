from decimal import Decimal

from coda.contexts.finance.dto.edit_position_dtos import AnyPositionDto, FreePositionDto
from coda.domain.invoice import AnyPosition, FundingSourceId, Position, PublicationCostType, TaxRate
from coda.domain.money import Currency, Money


def parse_item(position: FreePositionDto, *, parse_safe: bool = True) -> str:
    _ = parse_safe
    return position.description


def parse_cost_type(position: FreePositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def to_position(
    position: FreePositionDto, currency: Currency, *, parse_safe: bool = False
) -> Position[str]:
    return Position(
        item=parse_item(position, parse_safe=parse_safe),
        cost_type=parse_cost_type(position),
        cost=Money(position.cost_amount, currency),
        tax_rate=TaxRate.from_percentage(position.tax_rate),
        funding_source=FundingSourceId(position.funding_source)
        if position.funding_source
        else None,
        external_position_id=position.external_position_id,
    )


def position_to_dto(position: Position[str]) -> FreePositionDto:
    assert isinstance(position.item, str)
    is_vat = position.cost_type == PublicationCostType.Vat
    return FreePositionDto(
        description=position.item,
        funding_source=position.funding_source,
        cost_amount=position.cost.amount,
        cost_type=position.cost_type.value,
        tax_rate=Decimal("0.00") if is_vat else position.tax_rate.percentage(),
        external_position_id=position.external_position_id,
    )


class FreeParser:
    def to_position(
        self, position: AnyPositionDto, currency: Currency, *, parse_safe: bool = False
    ) -> AnyPosition:
        assert isinstance(position, FreePositionDto)
        return to_position(position, currency, parse_safe=parse_safe)

    def position_to_dto(self, position: AnyPosition) -> AnyPositionDto:
        assert isinstance(position, Position) and isinstance(position.item, str)
        return position_to_dto(position)


parser = FreeParser()

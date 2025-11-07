from typing_extensions import TypeIs

from coda.contexts.finance.dto.edit_position_dtos import (
    PositionDto,
    FreePositionDto,
    FundingAssignmentDto,
)
from coda.domain.finance import invoice_positions
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import FreeItem, Position
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


def parse_item(position: FreePositionDto, *, parse_safe: bool = True) -> str:
    _ = parse_safe
    return position.description


def parse_cost_type(position: FreePositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def to_position(
    position: FreePositionDto, currency: Currency, *, parse_safe: bool = False
) -> Position:
    _position = invoice_positions.create(
        item=FreeItem(
            parse_item(position, parse_safe=parse_safe),
            cost_type=parse_cost_type(position),
        ),
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


def position_to_dto(position: Position) -> FreePositionDto:
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
    )


def _is_freeitem(p: Position) -> TypeIs[Position]:
    return isinstance(p.item, FreeItem)


class FreeParser:
    def to_position(
        self, position: PositionDto, currency: Currency, *, parse_safe: bool = False
    ) -> Position:
        assert isinstance(position, FreePositionDto)
        return to_position(position, currency, parse_safe=parse_safe)

    def position_to_dto(self, position: Position) -> PositionDto:
        assert _is_freeitem(position)
        return position_to_dto(position)


parser = FreeParser()

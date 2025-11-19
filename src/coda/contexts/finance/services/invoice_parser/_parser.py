import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.dto.edit_position_dtos import (
    CommonPositionDto,
    FundingAssignmentDto,
    ItemDto,
    PositionDto,
    ContractPositionDto,
    FreePositionDto,
    PublicationPositionDto,
)
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.domain import errors
from coda.domain.contract import ContractYear
from coda.domain.finance import invoice_positions
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice
from coda.domain.finance.invoice_positions import Position, ItemType, PositionItemType
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId

from . import _contract, _free, _publication


class PositionParser(Protocol):
    def to_itemdto(self, position: Position) -> ItemDto:
        ...

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        ...


def parse_invoice(invoice_head: InvoiceHeadDto, positions: list[PositionDto]) -> Invoice:
    currency = invoice_head.currency
    with errors.capture(ValueError) as capture:
        parsed_positions = errors.results(
            capture(to_position, p, currency).map_err(PositionParseError, p) for p in positions
        )

    if parsed_positions.has_errors():
        raise InvoiceParseError(parsed_positions.errors())

    invoice = Invoice.new(
        **invoice_head.model_dump(exclude={"currency"}),
        positions=parsed_positions.values(),
    )

    return invoice


@dataclass
class InvoiceTotal:
    net: Decimal
    tax: Decimal
    total: Decimal


def invoice_total(positions: list[PositionDto], currency: Currency) -> InvoiceTotal:
    parsed = [to_position(p, currency, parse_safe=True) for p in positions]
    invoice = Invoice.new("", datetime.date.today(), CreditorId(0), parsed)

    return InvoiceTotal(
        net=invoice.net().amount,
        tax=invoice.tax().amount,
        total=invoice.total().amount,
    )


def to_position(position: PositionDto, currency: Currency, *, parse_safe: bool = False) -> Position:
    parser = _dto_parser_registry[position.type]

    _position = invoice_positions.create(
        item=parser.parse_item_from(position, parse_safe=parse_safe),
        cost=Money(position.cost_amount, currency),
        tax_rate=TaxRate.from_percentage(position.tax_rate),
        external_position_id=position.external_position_id,
        funding_source=FundingSourceId(position.funding_source)
        if position.funding_source
        else None,
    )

    _empty = FundingAssignmentDto()
    for f in position.funding_assignments:
        if f == _empty:
            continue

        fid = FundingSourceId(f.funding_source) if f.funding_source else None
        _position.assign_funding(fid, f.amount)

    return _position


def position_to_dto(position: Position) -> PositionDto:
    parser = _position_converters[type(position.item.item)]
    dto = _position_to_dto(position, parser.to_itemdto(position))
    fs = [
        fa.funding_source for fa in position.funding_assignments() if fa.funding_source is not None
    ]
    fs_types = funding_source_repository.types_for(fs)

    for fa_dto in dto.funding_assignments:
        if not fa_dto.funding_source:
            continue

        fs_type = fs_types.get(FundingSourceId(fa_dto.funding_source), "budget")
        fa_dto.funding_source_type = fs_type

    return dto


def _position_to_dto(position: Position, item_dto: ItemDto) -> CommonPositionDto:
    return CommonPositionDto(
        item=item_dto,
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


def get_position_type(type_name: str) -> type[PositionDto]:
    return _position_type_registry[type_name]


_position_type_registry: dict[str, type[PositionDto]] = {
    "publication": PublicationPositionDto,
    "free": FreePositionDto,
    "contract": ContractPositionDto,
}

_dto_parser_registry: dict[str, PositionParser] = {
    "publication": _publication.parser,
    "contract": _contract.parser,
    "free": _free.parser,
}

_position_converters: dict[type[ItemType], PositionParser] = {
    PublicationId: _publication.parser,
    ContractYear: _contract.parser,
    str: _free.parser,
}


class PositionParseError(Exception):
    def __init__(self, inner: Exception, position: PositionDto, *args: Any) -> None:
        super().__init__(*args)
        self.position = position
        self.inner = inner

    def message(self) -> str:
        return str(self.inner)


class InvoiceParseError(RuntimeError):
    def __init__(self, position_errors: list[PositionParseError]) -> None:
        super().__init__()
        self.position_errors = position_errors

    def error_for(self, position: PositionDto) -> PositionParseError | None:
        for err in self.position_errors:
            if position == err.position:
                return err
        return None

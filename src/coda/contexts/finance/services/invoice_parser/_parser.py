import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from coda.contexts.finance.dto.edit_position_dtos import (
    AnyPositionDto,
    CommonPositionDto,
    ContractPositionDto,
    FreePositionDto,
    PublicationPositionDto,
)
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.domain import errors
from coda.domain.contract import ContractYear
from coda.domain.invoice import (
    AnyPosition,
    CostType,
    CreditorId,
    Invoice,
    ItemType,
)
from coda.domain.money._currency import Currency
from coda.domain.publication.publication import PublicationId

from . import _contract, _free, _publication


class PositionParser(Protocol):
    def to_position(
        self, position: AnyPositionDto, currency: Currency, *, parse_safe: bool = True
    ) -> AnyPosition:
        ...

    def position_to_dto(self, position: AnyPosition) -> AnyPositionDto:
        ...


def parse_invoice(invoice_head: InvoiceHeadDto, positions: list[AnyPositionDto]) -> Invoice:
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


def invoice_total(positions: list[AnyPositionDto], currency: Currency) -> InvoiceTotal:
    parsed = [to_position(p, currency, parse_safe=True) for p in positions]
    invoice = Invoice.new("", datetime.date.today(), CreditorId(0), parsed)

    return InvoiceTotal(
        net=invoice.net().amount,
        tax=invoice.tax().amount,
        total=invoice.total().amount,
    )


def to_position(
    position: AnyPositionDto, currency: Currency, *, parse_safe: bool = False
) -> AnyPosition:
    parser = _dto_parser_registry[position.type]
    return parser.to_position(position, currency, parse_safe=parse_safe)


def position_to_dto(position: AnyPosition) -> AnyPositionDto:
    parser = _position_converters[type(position.item)]
    return parser.position_to_dto(position)


def position_type_names() -> list[str]:
    return list(_position_type_registry.keys())


def get_position_type(type_name: str) -> type[AnyPositionDto]:
    return _position_type_registry[type_name]


_position_type_registry: dict[str, type[CommonPositionDto[ItemType, CostType]]] = {
    "publication": PublicationPositionDto,
    "free": FreePositionDto,
    "contract": ContractPositionDto,
}

_dto_parser_registry: dict[str, PositionParser] = {
    "publication": _publication,
    "contract": _contract,
    "free": _free,
}

_position_converters: dict[type[ItemType], PositionParser] = {
    PublicationId: _publication,
    ContractYear: _contract,
    str: _free,
}


class PositionParseError(Exception):
    def __init__(self, inner: Exception, position: AnyPositionDto, *args: Any) -> None:
        super().__init__(*args)
        self.position = position
        self.inner = inner

    def message(self) -> str:
        return str(self.inner)


class InvoiceParseError(RuntimeError):
    def __init__(self, position_errors: list[PositionParseError]) -> None:
        super().__init__()
        self.position_errors = position_errors

    def error_for(self, position: AnyPositionDto) -> PositionParseError | None:
        for err in self.position_errors:
            if position == err.position:
                return err
        return None

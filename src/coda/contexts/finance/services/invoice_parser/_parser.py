import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol

from typing import TypeIs

from coda.contexts.finance.dto.edit_position_dtos import (
    FundingAssignmentDto,
    ItemDto,
    PositionDto,
)
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.domain import errors
from coda.domain.author import InstitutionId
from coda.domain.contract import ContractYear
from coda.domain.finance import invoice_positions
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice
from coda.domain.finance.invoice_positions import ItemType, Position, PositionItemType
from coda.domain.finance.taxable_money import CostBasis
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId

from . import _contract, _free, _publication


class PositionParser(Protocol):
    def to_itemdto(self, position: Position) -> ItemDto: ...

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType: ...


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
    )

    for f in position.funding_assignments:
        if f.funding_source is None and f.amount == 0:
            continue

        amount = position.cost_amount if _is_all_amount(f.amount) else f.amount

        fs: FundingSource | None
        match f:
            case FundingAssignmentDto(
                funding_source_type="budget",
                funding_source=int(funding_source),
            ):
                fs_id = FundingSourceId(funding_source)
                fs = Budget(fs_id, "")
            case FundingAssignmentDto(
                funding_source_type="institution",
                funding_source=int(funding_source),
            ):
                inst_id = InstitutionId(funding_source)
                fs = SplitSource.new(inst_id, "")
            case _:
                fs = None

        if fs is not None or not _is_all_amount(f.amount):
            _position.assign_funding(fs, amount, position.cost_basis_mode)

    return _position


def _is_all_amount(amount: Literal["all"] | Decimal) -> TypeIs[Literal["all"]]:
    return amount == "all"


def position_to_dto(position: Position, cost_basis: CostBasis = CostBasis.net) -> PositionDto:
    parser = _position_converters[type(position.item.item)]
    dto = _position_to_dto(position, parser.to_itemdto(position), cost_basis)

    return dto


def _position_to_dto(position: Position, item_dto: ItemDto, cost_basis: CostBasis) -> PositionDto:
    return PositionDto(
        item=item_dto,
        cost_amount=position.cost.amount,
        tax_rate=position.tax_rate.percentage(),
        external_position_id=position.external_position_id,
        funding_assignments=[
            FundingAssignmentDto(
                funding_source=f.funding_source.identity() if f.funding_source else None,
                funding_source_type=f.funding_source.kind() if f.funding_source else "budget",
                amount=f.amount.amount,
            )
            for f in position.funding_assignments(cost_basis)
            if f.funding_source or f.amount.amount != 0
        ],
        unassigned_costs=position.unassigned_costs(cost_basis).amount,
        cost_basis_mode=cost_basis,
    )


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

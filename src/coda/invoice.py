import datetime
import functools
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import Any, NamedTuple, NewType, Self

from coda.money import Currency, Money
from coda.publication import PublicationId

InvoiceId = NewType("InvoiceId", int)
PublisherId = NewType("PublisherId", int)
FundingSourceId = NewType("FundingSourceId", int)

PositionNumber = NewType("PositionNumber", int)


class Position(NamedTuple):
    number: PositionNumber
    publication: PublicationId
    cost: Money
    description: str = ""
    funding_source: FundingSourceId | None = None


def _ensure_unique(
    positions: Collection[Position], key: Callable[[Position], Any], message: str
) -> None:
    keys = {key(p) for p in positions}
    if len(keys) != len(positions):
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class Invoice:
    id: InvoiceId | None
    number: str
    date: datetime.date
    creditor: PublisherId
    positions: Iterable[Position]

    @classmethod
    def new(
        cls, number: str, date: datetime.date, creditor: PublisherId, positions: Iterable[Position]
    ) -> Self:
        return cls(None, number, date, creditor, positions)

    def __post_init__(self) -> None:
        _positions = tuple(self.positions)
        _ensure_unique(
            _positions,
            lambda p: p.number,
            "Cannot have multiple positions with the same number",
        )

        _ensure_unique(
            _positions,
            lambda p: p.publication,
            "Cannot have multiple positions for the same publication",
        )

    def total(self) -> Money:
        return functools.reduce(
            lambda acc, pos: acc + pos.cost, self.positions, Money(0, Currency.EUR)
        )

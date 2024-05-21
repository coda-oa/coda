import functools
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple, NewType, Self

from coda.money import Currency, Money
from coda.publication import PublicationId

InvoiceId = NewType("InvoiceId", int)
PublisherId = NewType("PublisherId", int)
FundingSourceId = NewType("FundingSourceId", int)


class Position(NamedTuple):
    publication: PublicationId
    cost: Money
    description: str = ""
    funding_source: FundingSourceId | None = None


@dataclass(frozen=True, slots=True)
class Invoice:
    id: InvoiceId | None
    recipient: PublisherId
    positions: Iterable[Position]

    @classmethod
    def new(cls, recipient: PublisherId, positions: Iterable[Position]) -> Self:
        return cls(None, recipient, positions)

    def __post_init__(self) -> None:
        _positions = tuple(self.positions)
        pub_ids = {p.publication for p in self.positions}
        if len(pub_ids) != len(_positions):
            raise ValueError("Cannot have multiple positions for the same publication")

    def total(self) -> Money:
        return functools.reduce(
            lambda acc, pos: acc + pos.cost, self.positions, Money(0, Currency.EUR)
        )

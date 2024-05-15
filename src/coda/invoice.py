import functools
from collections.abc import Iterable
from typing import NamedTuple, NewType, Self

from coda.money import Currency, Money
from coda.publication import PublicationId


PositionId = NewType("PositionId", int)
InvoiceId = NewType("InvoiceId", int)
RecipientId = NewType("RecipientId", int)


class Position(NamedTuple):
    id: PositionId | None
    publication: PublicationId
    cost: Money
    description: str = ""

    @classmethod
    def new(cls, publication: PublicationId, cost: Money, description: str = "") -> Self:
        return cls(None, publication, cost, description)


class Invoice(NamedTuple):
    id: InvoiceId | None
    recipient: RecipientId
    positions: Iterable[Position]

    @classmethod
    def new(cls, recipient: RecipientId, positions: Iterable[Position]) -> Self:
        _positions = tuple(positions)
        pub_ids = {p.publication for p in positions}
        if len(pub_ids) != len(_positions):
            raise ValueError("Cannot have multiple positions for the same publication")
        return cls(None, recipient, _positions)

    def total(self) -> Money:
        return functools.reduce(
            lambda acc, pos: acc + pos.cost, self.positions, Money(0, Currency.EUR)
        )

import datetime
import enum
import functools
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import Any, NamedTuple, NewType, Self

from coda.money import Currency, Money
from coda.publication import PublicationId

InvoiceId = NewType("InvoiceId", int)
CreditorId = NewType("CreditorId", int)
FundingSourceId = NewType("FundingSourceId", int)


class CostType(enum.Enum):
    """
    Enum representing the cost type based on the OpenCost schema.
    """

    Gold_OA = "gold-oa"
    Hybrid_OA = "hybrid-oa"
    Vat = "vat"
    Colour_Charge = "colour charge"
    Page_Charge = "page charge"
    Permission = "permission"
    Publication_Charge = "publication charge"
    Reprint = "reprint"
    Submission_Fee = "submission fee"
    Payment_Fee = "payment fee"
    Other = "other"


class Position(NamedTuple):
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
    creditor: CreditorId
    positions: Iterable[Position]
    comment: str = ""

    @classmethod
    def new(
        cls,
        number: str,
        date: datetime.date,
        creditor: CreditorId,
        positions: Iterable[Position],
        comment: str = "",
    ) -> Self:
        return cls(None, number, date, creditor, positions, comment)

    def total(self) -> Money:
        return functools.reduce(
            lambda acc, pos: acc + pos.cost, self.positions, Money(0, Currency.EUR)
        )

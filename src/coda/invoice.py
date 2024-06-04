import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple, NewType, Self

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
    tax_rate: float = 0.0
    description: str = ""
    funding_source: FundingSourceId | None = None


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

    def tax(self) -> Money:
        return sum((pos.cost * pos.tax_rate for pos in self.positions), Money(0, Currency.EUR))

    def net(self) -> Money:
        return sum((pos.cost for pos in self.positions), Money(0, Currency.EUR))

    def total(self) -> Money:
        return self.net() + self.tax()

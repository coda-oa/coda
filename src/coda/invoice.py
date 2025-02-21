import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, NamedTuple, NewType, Self, TypeVar

from coda.contract import ContractYear
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


class TaxRate(Decimal):
    __slots__ = ()

    def __new__(cls, value: Decimal | float | str) -> Self:
        v = Decimal(value)
        if v < 0:
            raise ValueError("Tax rate must be positive")

        return super().__new__(cls, v.quantize(Decimal("0.0000")))

    @classmethod
    def from_percentage(cls, value: Decimal | float | str) -> "TaxRate":
        return TaxRate(cls(value) / 100)

    def percentage(self) -> Decimal:
        return self * 100


ItemType = PublicationId | ContractYear | str
T = TypeVar("T", bound=ItemType, covariant=True)
Positions = Iterable["Position[ItemType]"]


class PaymentStatus(enum.Enum):
    Paid = "paid"
    Unpaid = "unpaid"
    Rejected = "rejected"


class Position(NamedTuple, Generic[T]):
    item: T
    cost: Money
    cost_type: CostType
    tax_rate: TaxRate = TaxRate(0)
    funding_source: FundingSourceId | None = None

    def net(self) -> Money:
        return self.cost

    def tax(self) -> Money:
        return self.cost * self.tax_rate

    def total(self) -> Money:
        return self.net() + self.tax()


@dataclass(slots=True)
class Invoice:
    id: InvoiceId | None
    number: str
    date: datetime.date
    creditor: CreditorId
    positions: Positions
    status: PaymentStatus = PaymentStatus.Unpaid
    comment: str = ""

    @classmethod
    def new(
        cls,
        number: str,
        date: datetime.date,
        creditor: CreditorId,
        positions: Positions,
        status: PaymentStatus = PaymentStatus.Unpaid,
        comment: str = "",
    ) -> Self:
        return cls(None, number, date, creditor, positions, status, comment)

    def currency(self) -> Currency:
        if not self.positions:
            return Currency.EUR

        return next(iter(self.positions)).cost.currency

    def tax(self) -> Money:
        return sum((pos.tax() for pos in self.positions), Money(0, self.currency()))

    def net(self) -> Money:
        return sum((pos.net() for pos in self.positions), Money(0, self.currency()))

    def total(self) -> Money:
        return self.net() + self.tax()

    def pay(self) -> None:
        self.status = PaymentStatus.Paid

    def reset_payment(self) -> None:
        self.status = PaymentStatus.Unpaid

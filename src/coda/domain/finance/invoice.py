import dataclasses
import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, NewType, Self

from coda.domain.contract import ContractYear
from coda.domain.money import Currency, CurrencyExchange, Money
from coda.domain.publication import PublicationId

if TYPE_CHECKING:
    from coda.domain.finance.invoice_positions import AnyPosition

InvoiceId = NewType("InvoiceId", int)
CreditorId = NewType("CreditorId", int)
FundingSourceId = NewType("FundingSourceId", int)


class PublicationCostType(enum.Enum):
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


class ContractCostType(enum.Enum):
    """
    Enum representing the cost type for contracts based on the OpenCost schema.
    """

    Publish = "publish"
    Read = "read"
    Vat = "vat"


ItemType = PublicationId | ContractYear | str
CostType = PublicationCostType | ContractCostType


type Positions = Iterable[AnyPosition]


class PaymentStatus(enum.Enum):
    Paid = "paid"
    Unpaid = "unpaid"
    Rejected = "rejected"


def _internal_exchange(exchange_rates: dict[Currency, Decimal]) -> CurrencyExchange:
    def _exchange(origin: Currency, target: Currency) -> Decimal:
        if origin == target:
            return Decimal("1.0")
        return exchange_rates[target]

    return _exchange


@dataclass(slots=True)
class Invoice:
    id: InvoiceId | None
    number: str
    date: datetime.date
    creditor: CreditorId
    positions: Positions
    status: PaymentStatus = PaymentStatus.Unpaid
    comment: str = ""
    external_invoice_id: str = ""

    _conversions: dict[Currency, Decimal] = field(default_factory=dict, init=False)

    @classmethod
    def new(
        cls,
        number: str,
        date: datetime.date,
        creditor: CreditorId,
        positions: Positions,
        status: PaymentStatus = PaymentStatus.Unpaid,
        comment: str = "",
        external_invoice_id: str = "",
    ) -> Self:
        return cls(None, number, date, creditor, positions, status, comment, external_invoice_id)

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

    def is_paid(self) -> bool:
        return self.status == PaymentStatus.Paid

    def pay(self) -> None:
        self.status = PaymentStatus.Paid

    def reset_payment(self) -> None:
        self.status = PaymentStatus.Unpaid

    def add_conversion(self, rate: Decimal, to_currency: Currency) -> None:
        """
        Adds a conversion rate for the invoice.
        """

        self._conversions[to_currency] = rate

    def remove_conversion(self, currency: Currency) -> None:
        """
        Removes a conversion rate for the invoice.
        """
        if currency not in self._conversions:
            raise NoSuchConversion(currency)

        del self._conversions[currency]

    def conversions(self) -> dict[Currency, Decimal]:
        """
        Returns a dictionary of currency conversions.
        The keys are the target currencies, and the values are the conversion rates.
        """
        return dict(self._conversions)

    def clear_conversions(self) -> None:
        self._conversions.clear()

    def convert(self, to: Currency) -> "Invoice":
        """
        Returns a new Invoice with all positions converted to the specified currency.
        """
        if to == self.currency():
            return self

        if to not in self._conversions:
            raise NoSuchConversion(to)

        exchange = _internal_exchange(self.conversions())

        converted_positions = [pos.convert(to, exchange) for pos in self.positions]
        converted = dataclasses.replace(self, positions=converted_positions)
        converted._conversions = self._convert_exchange_rates(to)

        return converted

    def _convert_exchange_rates(self, to: Currency) -> dict[Currency, Decimal]:
        reverse_self_conversion = {self.currency(): 1 / self._conversions[to]}
        converted_exchange_rates = {
            k: v / self._conversions[to] for k, v in self._conversions.items() if k != to
        }

        return reverse_self_conversion | converted_exchange_rates


class NoSuchConversion(Exception):
    """
    Exception raised when a conversion to a specific currency is not available.
    """

    def __init__(self, currency: Currency) -> None:
        super().__init__(f"No conversion available for {currency.value}")
        self.currency = currency

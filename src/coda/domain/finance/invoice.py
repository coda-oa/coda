import datetime
import enum
from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING, Self

from coda.domain import errors
from coda.domain.money import Currency, CurrencyExchange, Money
from coda.entityid import EntityId

if TYPE_CHECKING:
    from coda.domain.finance.invoice_positions import Position

# InvoiceId = NewType("InvoiceId", int)
# CreditorId = NewType("CreditorId", int)
# FundingSourceId = NewType("FundingSourceId", int)


class InvoiceId(EntityId): ...


class CreditorId(EntityId): ...


class FundingSourceId(EntityId): ...


type Positions = Iterable[Position]


class PaymentStatus(enum.Enum):
    Paid = "paid"
    Unpaid = "unpaid"
    Rejected = "rejected"


class UnassignedCosts(errors.DomainError):
    pass


def _internal_exchange(exchange_rates: dict[Currency, Decimal]) -> CurrencyExchange:
    def _exchange(origin: Currency, target: Currency) -> Decimal:
        if origin == target:
            return Decimal("1.0")
        return exchange_rates[target]

    return _exchange


class Invoice:
    def __init__(
        self,
        id: InvoiceId,
        number: str,
        date: datetime.date,
        creditor: CreditorId,
        positions: Positions,
        status: PaymentStatus = PaymentStatus.Unpaid,
        comment: str = "",
        external_invoice_id: str = "",
    ) -> None:
        self.id = id
        self.number = number
        self.date = date
        self.creditor = creditor
        self._positions = positions
        self.status = status
        self.comment = comment
        self.external_invoice_id = external_invoice_id
        self._conversions: dict[Currency, Decimal] = {}

        if self.is_paid() and not self._all_costs_assigned(positions):
            raise UnassignedCosts()

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
        return cls(
            InvoiceId(), number, date, creditor, positions, status, comment, external_invoice_id
        )

    @property
    def positions(self) -> Positions:
        return tuple(self._positions)

    @positions.setter
    def positions(self, value: Positions) -> None:
        if self.is_paid() and not self._all_costs_assigned(value):
            raise UnassignedCosts()

        self._positions = tuple(value)

    def _all_costs_assigned(self, positions: Positions) -> bool:
        return all(p.unassigned_costs() == Money(0, self.currency()) for p in positions)

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

    def unassigned_costs(self) -> Money:
        return sum((p.unassigned_costs() for p in self.positions), start=Money(0, self.currency()))

    def is_paid(self) -> bool:
        return self.status == PaymentStatus.Paid

    def pay(self) -> None:
        if not self._all_costs_assigned(self.positions):
            raise UnassignedCosts()

        self.status = PaymentStatus.Paid

    def reject(self) -> None:
        self.status = PaymentStatus.Rejected

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
        converted = self._replace_positions(converted_positions)
        converted._conversions = self._convert_exchange_rates(to)

        return converted

    def _convert_exchange_rates(self, to: Currency) -> dict[Currency, Decimal]:
        reverse_self_conversion = {self.currency(): 1 / self._conversions[to]}
        converted_exchange_rates = {
            k: v / self._conversions[to] for k, v in self._conversions.items() if k != to
        }

        return reverse_self_conversion | converted_exchange_rates

    def _replace_positions(self, converted_positions: Positions) -> "Invoice":
        return Invoice(
            self.id,
            self.number,
            self.date,
            self.creditor,
            converted_positions,
            self.status,
            self.comment,
            self.external_invoice_id,
        )


class NoSuchConversion(Exception):
    """
    Exception raised when a conversion to a specific currency is not available.
    """

    def __init__(self, currency: Currency) -> None:
        super().__init__(f"No conversion available for {currency.value}")
        self.currency = currency

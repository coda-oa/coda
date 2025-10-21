import dataclasses
import datetime
import enum
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import Generic, NewType, Protocol, Self, TypeVar

from coda.domain.contract import ContractYear
from coda.domain.errors import DomainError
from coda.domain.money import Currency, Money
from coda.domain.money._money import CurrencyExchange
from coda.domain.publication import PublicationId

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


class TaxRate(Decimal):
    __slots__ = ()

    def __new__(cls, value: Decimal | float | str) -> Self:
        v = Decimal(value)
        if v < 0:
            raise DomainError("Tax rate must be positive")

        return super().__new__(cls, v.quantize(Decimal("0.0000")))

    @classmethod
    def from_percentage(cls, value: Decimal | float | str) -> "TaxRate":
        return TaxRate(cls(value) / 100)

    def percentage(self) -> Decimal:
        return self * 100


ItemType = PublicationId | ContractYear | str
CostType = PublicationCostType | ContractCostType
BaseItemT = TypeVar("BaseItemT")
BaseCostTypeT = TypeVar("BaseCostTypeT", bound=enum.Enum)


class Item(Protocol, Generic[BaseItemT, BaseCostTypeT]):
    item: BaseItemT
    cost_type: BaseCostTypeT


@dataclass(slots=True)
class PublicationItem(Item[PublicationId, PublicationCostType]):
    item: PublicationId
    cost_type: PublicationCostType


@dataclass(slots=True)
class ContractItem(Item[ContractYear, ContractCostType]):
    item: ContractYear
    cost_type: ContractCostType


@dataclass(slots=True)
class FreeItem(Item[str, PublicationCostType]):
    item: str
    cost_type: PublicationCostType


PositionItemType = PublicationItem | ContractItem | FreeItem
ItemT = TypeVar("ItemT", PublicationItem, ContractItem, FreeItem)
type AnyPosition = PublicationPosition | ContractPosition | FreePosition
type Positions = Iterable[AnyPosition]


class PaymentStatus(enum.Enum):
    Paid = "paid"
    Unpaid = "unpaid"
    Rejected = "rejected"


class CostCalculation(Protocol):
    def tax_rate(self) -> TaxRate:
        ...

    def net(self) -> Decimal:
        ...

    def tax(self) -> Decimal:
        ...

    def total(self) -> Decimal:
        ...


@dataclass(slots=True, frozen=True)
class RegularCostCalculation:
    cost: Decimal
    the_tax_rate: TaxRate

    def tax_rate(self) -> TaxRate:
        return self.the_tax_rate

    def net(self) -> Decimal:
        return self.cost

    def tax(self) -> Decimal:
        return self.cost * self.the_tax_rate

    def total(self) -> Decimal:
        return self.net() + self.tax()


@dataclass(slots=True, frozen=True)
class VatCalculation:
    cost: Decimal

    def tax_rate(self) -> TaxRate:
        return TaxRate.from_percentage(0)

    def net(self) -> Decimal:
        return Decimal(0)

    def tax(self) -> Decimal:
        return self.cost

    def total(self) -> Decimal:
        return self.tax()


class CommonPosition(ABC, Generic[ItemT, BaseItemT, BaseCostTypeT]):
    def __init__(
        self,
        *,
        item: ItemT,
        cost: Money,
        tax_rate: TaxRate,
        funding_source: FundingSourceId | None = None,
        external_position_id: str = "",
    ) -> None:
        self.cost = cost
        self.funding_source = funding_source
        self.external_position_id = external_position_id
        self._tax_rate = tax_rate

        self._item: ItemT = item

    @cached_property
    def _cost_calculation(self) -> CostCalculation:
        if self.cost_type.value == "vat":
            return VatCalculation(self.cost.amount)
        else:
            return RegularCostCalculation(self.cost.amount, self._tax_rate)

    @abstractmethod
    def convert(
        self, to: Currency, exchange: CurrencyExchange
    ) -> "CommonPosition[ItemT, BaseItemT, BaseCostTypeT]":
        ...

    @property
    @abstractmethod
    def item(self) -> BaseItemT:
        ...

    @property
    @abstractmethod
    def cost_type(self) -> BaseCostTypeT:
        ...

    @property
    def tax_rate(self) -> TaxRate:
        return self._cost_calculation.tax_rate()

    def net(self) -> Money:
        return Money(self._cost_calculation.net(), self.cost.currency)

    def tax(self) -> Money:
        return Money(self._cost_calculation.tax(), self.cost.currency)

    def total(self) -> Money:
        return Money(self._cost_calculation.total(), self.cost.currency)

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, self.__class__):
            return False

        return (
            self.cost == value.cost
            and self.tax_rate == value.tax_rate
            and self.funding_source == value.funding_source
            and self.external_position_id == value.external_position_id
        )

    def __hash__(self) -> int:
        return hash((self.cost, self.tax_rate, self.funding_source, self.external_position_id))


class PublicationPosition(CommonPosition[PublicationItem, PublicationId, PublicationCostType]):
    def convert(self, to: Currency, exchange: CurrencyExchange) -> "PublicationPosition":
        return PublicationPosition(
            item=self._item,
            cost=self.cost.convert_to(to, exchange),
            tax_rate=self.tax_rate,
            funding_source=self.funding_source,
            external_position_id=self.external_position_id,
        )

    @property
    def item(self) -> PublicationId:
        return self._item.item

    @property
    def cost_type(self) -> PublicationCostType:
        return self._item.cost_type


class ContractPosition(CommonPosition[ContractItem, ContractYear, ContractCostType]):
    def convert(self, to: Currency, exchange: CurrencyExchange) -> "ContractPosition":
        return ContractPosition(
            item=self._item,
            cost=self.cost.convert_to(to, exchange),
            tax_rate=self.tax_rate,
            funding_source=self.funding_source,
            external_position_id=self.external_position_id,
        )

    @property
    def item(self) -> ContractYear:
        return self._item.item

    @property
    def cost_type(self) -> ContractCostType:
        return self._item.cost_type


class FreePosition(CommonPosition[FreeItem, str, PublicationCostType]):
    def convert(self, to: Currency, exchange: CurrencyExchange) -> "FreePosition":
        return FreePosition(
            item=self._item,
            cost=self.cost.convert_to(to, exchange),
            tax_rate=self.tax_rate,
            funding_source=self.funding_source,
            external_position_id=self.external_position_id,
        )

    @property
    def item(self) -> str:
        return self._item.item

    @property
    def cost_type(self) -> PublicationCostType:
        return self._item.cost_type


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

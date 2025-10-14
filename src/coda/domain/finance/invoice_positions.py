import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, Protocol, TypeVar

from coda.domain import errors
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency
from coda.domain.money._money import CurrencyExchange, Money
from coda.domain.publication.publication import PublicationId

BaseItemT = TypeVar("BaseItemT")
BaseCostTypeT = TypeVar("BaseCostTypeT", bound=enum.Enum)


class SplitTooLarge(errors.DomainError):
    pass


class InvalidSplitAmount(errors.DomainError):
    pass


class SameFundingSource(errors.DomainError):
    pass


def _sign(x: Decimal) -> int:
    return 1 if x >= 0 else -1


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


type ItemType = PublicationId | ContractYear | str
type PositionItemType = PublicationItem | ContractItem | FreeItem
type AnyPosition = "Position[PublicationItem] | Position[ContractItem] | Position[FreeItem]"


class CostCalculation(Protocol):
    @property
    def cost(self) -> Money: ...

    def tax_rate(self) -> TaxRate: ...

    def net(self) -> Money: ...

    def tax(self) -> Money: ...

    def total(self) -> Money: ...

    def convert(self, to: Currency, exchange: CurrencyExchange) -> "CostCalculation": ...


@dataclass(slots=True, frozen=True)
class RegularCostCalculation:
    cost: Money
    the_tax_rate: TaxRate

    def tax_rate(self) -> TaxRate:
        return self.the_tax_rate

    def net(self) -> Money:
        return self.cost

    def tax(self) -> Money:
        return Money(self.cost.amount * self.the_tax_rate, self.cost.currency)

    def total(self) -> Money:
        return self.net() + self.tax()

    def convert(self, to: Currency, exchange: CurrencyExchange) -> CostCalculation:
        return RegularCostCalculation(self.cost.convert_to(to, exchange), self.tax_rate())


@dataclass(slots=True, frozen=True)
class VatCalculation:
    cost: Money

    def tax_rate(self) -> TaxRate:
        return TaxRate.from_percentage(0)

    def net(self) -> Money:
        return Money(0, self.cost.currency)

    def tax(self) -> Money:
        return self.cost

    def total(self) -> Money:
        return self.tax()

    def convert(self, to: Currency, exchange: CurrencyExchange) -> CostCalculation:
        return VatCalculation(self.cost.convert_to(to, exchange))


ItemT = TypeVar("ItemT", PublicationItem, ContractItem, FreeItem, covariant=True)


class _CommonPosition(Generic[ItemT]):
    def __init__(
        self,
        *,
        item: ItemT,
        funding_source: FundingSourceId | None = None,
        external_position_id: str = "",
        cost_calculation: CostCalculation,
    ) -> None:
        self.funding_source = funding_source
        self.external_position_id = external_position_id

        self._item: ItemT = item
        self._cost_calculation = cost_calculation
        self._splits: list[tuple[FundingSourceId | None, Money]] = []

    @property
    def cost(self) -> Money:
        return self._cost_calculation.cost

    @property
    def item(self) -> ItemT:
        return self._item

    @property
    def tax_rate(self) -> TaxRate:
        return self._cost_calculation.tax_rate()

    def net(self) -> Money:
        return self._cost_calculation.net()

    def tax(self) -> Money:
        return self._cost_calculation.tax()

    def total(self) -> Money:
        return self._cost_calculation.total()

    def convert(self, to: Currency, exchange: CurrencyExchange) -> "Position[ItemT]":
        return _CommonPosition(
            item=self._item,
            funding_source=self.funding_source,
            external_position_id=self.external_position_id,
            cost_calculation=self._cost_calculation.convert(to, exchange),
        )

    def unassigned_costs(self) -> Money:
        if not self._splits:
            return Money(0, self.cost.currency)
        return self._get_split_remainder()

    def add_split(self, funding_source: FundingSourceId, amount: Decimal) -> None:
        if self._is_invalid_split_amount(amount):
            raise InvalidSplitAmount()

        self._splits.append((funding_source, Money(amount, self.cost.currency)))

    def participants(self) -> list[tuple[FundingSourceId | None, Money]]:
        remaining_costs = self._get_split_remainder()

        return [(self.funding_source, remaining_costs)] + self._splits

    def _is_invalid_split_amount(self, amount: Decimal) -> bool:
        sign_not_equal = _sign(self.cost.amount) != _sign(amount)
        split_too_large = abs(amount) >= abs(self._get_split_remainder().amount)
        return sign_not_equal or split_too_large

    def _get_split_remainder(self) -> Money:
        split_costs = sum(
            (amount for _, amount in self._splits), start=Money(0, self.cost.currency)
        )
        remaining_costs = self.cost - split_costs
        return remaining_costs

    def _funding_sources(self) -> set[FundingSourceId | None]:
        fs = {fs for fs, _ in self._splits}
        fs.add(self.funding_source)
        return fs

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, self.__class__):
            return False

        return (
            self.item == value.item
            and self.cost == value.cost
            and self.tax_rate == value.tax_rate
            and self.funding_source == value.funding_source
            and self.external_position_id == value.external_position_id
        )

    def __hash__(self) -> int:
        return hash(
            (self.item, self.cost, self.tax_rate, self.funding_source, self.external_position_id)
        )

    def __repr__(self) -> str:
        return f"""
        CommonPosition(
            item={repr(self.item)},
            cost={self.cost},
            tax_rate={self.tax_rate},
            funding_source={self.funding_source},
            external_position_id={self.external_position_id}
        )
        """


def create(
    item: ItemT,
    cost: Money,
    tax_rate: TaxRate,
    funding_source: FundingSourceId | None = None,
    external_position_id: str = "",
) -> "Position[ItemT]":
    if item.cost_type.is_vat():
        return vat(item, cost, funding_source, external_position_id)

    return regular(item, cost, tax_rate, funding_source, external_position_id)


def regular(
    item: ItemT,
    cost: Money,
    tax_rate: TaxRate,
    funding_source: FundingSourceId | None = None,
    external_position_id: str = "",
) -> "Position[ItemT]":
    return _CommonPosition(
        item=item,
        funding_source=funding_source,
        external_position_id=external_position_id,
        cost_calculation=RegularCostCalculation(cost, tax_rate),
    )


def vat(
    item: ItemT,
    cost: Money,
    funding_source: FundingSourceId | None = None,
    external_position_id: str = "",
) -> "Position[ItemT]":
    return _CommonPosition(
        item=item,
        funding_source=funding_source,
        external_position_id=external_position_id,
        cost_calculation=VatCalculation(cost),
    )


class Position(Protocol[ItemT]):
    @property
    def funding_source(self) -> FundingSourceId | None: ...

    @property
    def external_position_id(self) -> str: ...

    @property
    def cost(self) -> Money: ...

    @property
    def item(self) -> ItemT: ...

    @property
    def tax_rate(self) -> TaxRate: ...

    def net(self) -> Money: ...

    def tax(self) -> Money: ...

    def total(self) -> Money: ...

    def convert(self, to: Currency, exchange: CurrencyExchange) -> "Position[ItemT]": ...

    def unassigned_costs(self) -> Money: ...

    def add_split(self, funding_source: FundingSourceId, amount: Decimal) -> None: ...

    def participants(self) -> list[tuple[FundingSourceId | None, Money]]: ...

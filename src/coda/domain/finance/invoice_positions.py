from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from coda.domain import errors
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, CurrencyExchange, Money
from coda.domain.publication.publication import PublicationId


class SplitTooLarge(errors.DomainError):
    pass


class InvalidSplitAmount(errors.DomainError):
    pass


class SameFundingSource(errors.DomainError):
    pass


def _sign(x: Decimal) -> int:
    return 1 if x >= 0 else -1


@dataclass(slots=True)
class PublicationItem:
    item: PublicationId
    cost_type: PublicationCostType


@dataclass(slots=True)
class ContractItem:
    item: ContractYear
    cost_type: ContractCostType


@dataclass(slots=True)
class FreeItem:
    item: str
    cost_type: PublicationCostType


type ItemType = PublicationId | ContractYear | str
type PositionItemType = PublicationItem | ContractItem | FreeItem


class CostCalculation(Protocol):
    @property
    def cost(self) -> Money:
        ...

    def tax_rate(self) -> TaxRate:
        ...

    def net(self) -> Money:
        ...

    def tax(self) -> Money:
        ...

    def total(self) -> Money:
        ...

    def convert(self, to: Currency, exchange: CurrencyExchange) -> "CostCalculation":
        ...

    def normalize(self, amount: Decimal, *, is_gross: bool) -> Decimal:
        ...


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

    def normalize(self, amount: Decimal, *, is_gross: bool) -> Decimal:
        return amount / (Decimal(1) + self.tax_rate()) if is_gross else amount


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

    def normalize(self, amount: Decimal, *, is_gross: bool) -> Decimal:
        _ = is_gross
        return amount


@dataclass(frozen=True)
class FundingAssignment:
    funding_source: FundingSourceId | None
    amount: Money


class Position:
    def __init__(
        self,
        *,
        item: PositionItemType,
        funding_source: FundingSourceId | None = None,
        external_position_id: str = "",
        cost_calculation: CostCalculation,
    ) -> None:
        self.funding_source = funding_source
        self.external_position_id = external_position_id

        self._item = item
        self._cost_calculation = cost_calculation
        self._splits: list[FundingAssignment] = []

    @property
    def cost(self) -> Money:
        return self._cost_calculation.cost

    @property
    def item(self) -> PositionItemType:
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

    def convert(self, to: Currency, exchange: CurrencyExchange) -> "Position":
        return Position(
            item=self._item,
            funding_source=self.funding_source,
            external_position_id=self.external_position_id,
            cost_calculation=self._cost_calculation.convert(to, exchange),
        )

    def as_gross(self, amount: Decimal) -> Decimal:
        return amount * (Decimal(1) + self.tax_rate)

    def unassigned_costs(self, *, as_gross: bool = False) -> Money:
        if not self._splits:
            return Money(0, self.cost.currency)
        remainder = self._get_split_remainder()

        if as_gross:
            remainder = self._to_gross(remainder)

        return remainder

    def assign_funding(
        self, funding_source: FundingSourceId | None, amount: Decimal, *, is_gross: bool = False
    ) -> None:
        amount = self._cost_calculation.normalize(amount, is_gross=is_gross)

        if self._is_invalid_split_amount(amount):
            raise InvalidSplitAmount()

        self._splits.append(FundingAssignment(funding_source, Money(amount, self.cost.currency)))

    def funding_assignments(self, *, as_gross: bool = False) -> list[FundingAssignment]:
        if as_gross:
            return [
                FundingAssignment(f.funding_source, self._to_gross(f.amount)) for f in self._splits
            ]

        return self._splits

    def _to_gross(self, amount: Money) -> Money:
        return Money(amount.amount * (Decimal(1) + self.tax_rate), amount.currency)

    def _is_invalid_split_amount(self, amount: Decimal) -> bool:
        sign_not_equal = _sign(self.cost.amount) != _sign(amount)
        split_too_large = abs(amount) > abs(self._get_split_remainder().amount)
        return sign_not_equal or split_too_large

    def _get_split_remainder(self) -> Money:
        split_costs = sum(
            (fund.amount for fund in self._splits), start=Money(0, self.cost.currency)
        )
        remaining_costs = self.cost - split_costs
        return remaining_costs

    def _funding_sources(self) -> set[FundingSourceId | None]:
        fs = {funds.funding_source for funds in self._splits}
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
            and self.funding_assignments() == value.funding_assignments()
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
            external_position_id={self.external_position_id},
            funding_assignments={repr(self.funding_assignments())},
        )
        """


def create(
    item: PositionItemType,
    cost: Money,
    tax_rate: TaxRate,
    funding_source: FundingSourceId | None = None,
    external_position_id: str = "",
) -> "Position":
    if item.cost_type.is_vat():
        return vat(item, cost, funding_source, external_position_id)

    return regular(item, cost, tax_rate, funding_source, external_position_id)


def regular(
    item: PositionItemType,
    cost: Money,
    tax_rate: TaxRate,
    funding_source: FundingSourceId | None = None,
    external_position_id: str = "",
) -> "Position":
    return Position(
        item=item,
        funding_source=funding_source,
        external_position_id=external_position_id,
        cost_calculation=RegularCostCalculation(cost, tax_rate),
    )


def vat(
    item: PositionItemType,
    cost: Money,
    funding_source: FundingSourceId | None = None,
    external_position_id: str = "",
) -> "Position":
    return Position(
        item=item,
        funding_source=funding_source,
        external_position_id=external_position_id,
        cost_calculation=VatCalculation(cost),
    )

import enum
from dataclasses import dataclass
from decimal import Decimal

from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


class CostBasis(enum.StrEnum):
    net = enum.auto()
    gross = enum.auto()


@dataclass
class NetMoney:
    base: Money
    tax_rate: TaxRate

    def __init__(self, amount: Decimal | str | int, currency: Currency, tax_rate: TaxRate) -> None:
        self.base = Money(amount, currency)
        self.tax_rate = tax_rate

    @classmethod
    def from_money(cls, money: Money, tax_rate: TaxRate) -> "NetMoney":
        return NetMoney(money.amount, money.currency, tax_rate)

    @classmethod
    def from_basis(cls, basis: CostBasis, money: Money, tax_rate: TaxRate) -> "NetMoney":
        if basis is CostBasis.gross:
            return NetMoney(money.amount / (Decimal(1) + tax_rate), money.currency, tax_rate)

        return NetMoney.from_money(money, tax_rate)

    @property
    def amount(self) -> Decimal:
        return self.base.amount

    @property
    def currency(self) -> Currency:
        return self.base.currency

    def amount_in(self, basis: CostBasis, /) -> Money:
        if basis is CostBasis.net:
            return self.base

        return self.as_gross()

    def as_gross(self) -> Money:
        return Money(self.amount * (Decimal(1) + self.tax_rate), self.currency)

    def tax_only(self) -> Money:
        return Money(self.amount * self.tax_rate, self.currency)

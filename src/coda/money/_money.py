from decimal import Decimal
from types import NotImplementedType
from typing import Protocol

from ._currency import Currency


class CurrencyExchange(Protocol):
    def __call__(self, origin: Currency, target: Currency) -> Decimal:
        ...


class Money:
    def __init__(self, amount: str | int | Decimal, currency: Currency) -> None:
        self.amount = self._half_round_up(currency, Decimal(amount))
        self.currency = currency

    def convert_to(self, target_currency: Currency, exchange: CurrencyExchange) -> "Money":
        if self.currency == target_currency:
            return self

        return Money(self._exchanged(target_currency, exchange), target_currency)

    def _exchanged(self, target_currency: Currency, exchange: CurrencyExchange) -> Decimal:
        return self.amount * exchange(self.currency, target_currency)

    def _half_round_up(self, target_currency: Currency, ex: Decimal) -> Decimal:
        return ex.quantize(
            Decimal("0.1") ** target_currency.minor_units,
            rounding="ROUND_HALF_UP",
        )

    def __eq__(self, v: object) -> bool | NotImplementedType:
        return self.amount == self._comparable_money(v).amount

    def __lt__(self, v: object) -> bool | NotImplementedType:
        return self.amount < self._comparable_money(v).amount

    def __le__(self, v: object) -> bool | NotImplementedType:
        return self.amount <= self._comparable_money(v).amount

    def _comparable_money(self, v: object) -> "Money":
        if not isinstance(v, Money):
            raise TypeError("Cannot compare money to non-money")

        if self.amount == 0 and v.amount == 0:
            return v

        if self.currency != v.currency:
            raise TypeError("Cannot compare money in different currencies")

        return v

    def __repr__(self) -> str:
        return f"Money({self.amount}, {self.currency})"

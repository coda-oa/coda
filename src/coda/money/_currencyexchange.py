from decimal import Decimal
from typing import Protocol

from coda.money import Currency


class ExchangeProvider(Protocol):
    def __call__(self, currency: Currency) -> dict[Currency, Decimal]:
        ...


class CachingCurrencyExchange:
    def __init__(
        self, cache: dict[Currency, dict[Currency, Decimal]], exchange_provider: ExchangeProvider
    ) -> None:
        self.cache = cache
        self.exchange_provider = exchange_provider

    def rate(self, from_currency: Currency, to_currency: Currency) -> Decimal:
        try:
            return self.cache[from_currency][to_currency]
        except KeyError:
            self.cache[from_currency] = self.exchange_provider(from_currency)
            return self.exchange_provider(from_currency)[to_currency]

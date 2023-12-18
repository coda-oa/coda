from decimal import Decimal
from typing import Protocol, TypeAlias

from coda.money import Currency

Rates: TypeAlias = dict[Currency, Decimal]
RatesLookup: TypeAlias = dict[Currency, Rates]


class ExchangeProvider(Protocol):
    def __call__(self, currency: Currency) -> Rates:
        ...


class CachingCurrencyExchange:
    def __init__(self, cache: RatesLookup, exchange_provider: ExchangeProvider) -> None:
        self.cache = cache
        self.exchange_provider = exchange_provider

    def rate(self, from_currency: Currency, to_currency: Currency) -> Decimal:
        try:
            return self.cache[from_currency][to_currency]
        except KeyError:
            self.cache[from_currency] = self.exchange_provider(from_currency)
            return self.exchange_provider(from_currency)[to_currency]

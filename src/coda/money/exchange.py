from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, NamedTuple, Protocol, TypeAlias

from coda.money import Currency

Rates: TypeAlias = dict[Currency, Decimal]


class RatesSnapshot(NamedTuple):
    timestamp: float
    rates: Rates


RatesLookup: TypeAlias = dict[Currency, RatesSnapshot]


class ExchangeProvider(Protocol):
    def __call__(self, currency: Currency) -> Rates:
        ...


Calendar: TypeAlias = Callable[[], datetime]


class CachingCurrencyExchange:
    def __init__(
        self,
        cache: RatesLookup,
        exchange_provider: ExchangeProvider,
        calendar: Calendar = datetime.now,
    ) -> None:
        self.cache = cache
        self.exchange_provider = exchange_provider
        self.calendar = calendar

    def rate(self, from_currency: Currency, to_currency: Currency) -> Decimal:
        try:
            return self._rate_from_cache(from_currency).rates[to_currency]
        except KeyError:
            rates = self.exchange_provider(from_currency)
            self._store(from_currency, rates)
            return rates[to_currency]

    def _rate_from_cache(self, from_currency: Currency) -> RatesSnapshot:
        cached = self.cache[from_currency]
        if self._expired(cached.timestamp):
            raise KeyError

        return cached

    def _expired(self, timestamp: float) -> bool:
        return self.calendar() >= datetime.fromtimestamp(timestamp) + timedelta(days=1)

    def _store(self, from_currency: Currency, rates: Rates) -> None:
        self.cache[from_currency] = RatesSnapshot(
            timestamp=self.calendar().timestamp(),
            rates=rates,
        )

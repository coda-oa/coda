from datetime import datetime, timedelta
from decimal import Decimal

from coda.money.exchange import (
    CachingCurrencyExchange,
    Calendar,
    Currency,
    Rates,
    RatesLookup,
    RatesSnapshot,
)


class ExchangeProviderStub:
    def __init__(self, rates: RatesLookup) -> None:
        self.rates = rates

    def __call__(self, currency: Currency) -> Rates:
        return self.rates[currency].rates


EXPECTED_USD_RATE = Decimal(2)
EXPECTED_GBP_RATE = Decimal(1.5)

NOW = datetime(year=2023, month=12, day=18)
TOMORROW = datetime(year=2023, month=12, day=19)


def eur_rates() -> RatesLookup:
    return {
        Currency.EUR: RatesSnapshot(
            timestamp=NOW.timestamp(),
            rates={
                Currency.USD: EXPECTED_USD_RATE,
                Currency.GBP: EXPECTED_GBP_RATE,
            },
        ),
    }


def calendar() -> datetime:
    return NOW


def empty_cache() -> RatesLookup:
    return {}


def make_sut(
    cache: RatesLookup = eur_rates(),
    exchange_provider: ExchangeProviderStub | None = None,
    calendar: Calendar = calendar,
) -> CachingCurrencyExchange:
    return CachingCurrencyExchange(
        cache=cache,
        exchange_provider=exchange_provider or ExchangeProviderStub({}),
        calendar=calendar,
    )


def test__caching_currency_exchange__returns_rate_from_cache() -> None:
    sut = make_sut()

    assert sut.rate(Currency.EUR, Currency.USD) == EXPECTED_USD_RATE
    assert sut.rate(Currency.EUR, Currency.GBP) == EXPECTED_GBP_RATE


def test__caching_currency_exchange__when_rate_not_in_cache__pulls_from_exchange_provider() -> None:
    exchange_provider = ExchangeProviderStub(eur_rates())
    sut = make_sut(empty_cache(), exchange_provider)

    assert sut.rate(Currency.EUR, Currency.USD) == EXPECTED_USD_RATE
    assert sut.rate(Currency.EUR, Currency.GBP) == EXPECTED_GBP_RATE


def test__caching_currency_exchange__when_rate_not_in_cache__adds_rates_and_timestamp_to_cache() -> (
    None
):
    cache = empty_cache()
    exchange_provider = ExchangeProviderStub(eur_rates())
    sut = make_sut(cache, exchange_provider)

    sut.rate(Currency.EUR, Currency.USD)

    assert cache == eur_rates()


def new_rates() -> RatesLookup:
    return {
        Currency.EUR: RatesSnapshot(
            timestamp=TOMORROW.timestamp(),
            rates={
                Currency.USD: Decimal(3),
                Currency.GBP: Decimal(2),
            },
        )
    }


def test__cached_rates_a_day_old__pulls_new_rates_from_exchange_provider() -> None:
    cache = eur_rates()
    exchange_provider = ExchangeProviderStub(new_rates())
    sut = make_sut(cache, exchange_provider, calendar=lambda: TOMORROW)

    sut.rate(Currency.EUR, Currency.USD)

    assert cache == new_rates()


def test__cached_rates_less_than_a_day_old__does_not_pull_new_rates_from_exchange_provider() -> (
    None
):
    def not_quite_tomorrow():
        return TOMORROW - timedelta(seconds=1)

    cache = eur_rates()
    exchange_provider = ExchangeProviderStub(new_rates())
    sut = make_sut(cache, exchange_provider, calendar=not_quite_tomorrow)

    sut.rate(Currency.EUR, Currency.GBP)

    assert cache == eur_rates()

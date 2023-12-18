from decimal import Decimal

from coda.money import CachingCurrencyExchange, Currency, Rates, RatesLookup


class ExchangeProviderStub:
    def __init__(self, rates: RatesLookup) -> None:
        self.rates = rates

    def __call__(self, currency: Currency) -> Rates:
        return self.rates[currency]


EXPECTED_USD_RATE = Decimal(2)
EXPECTED_GBP_RATE = Decimal(1.5)


def eur_rates() -> RatesLookup:
    return {
        Currency.EUR: {
            Currency.USD: EXPECTED_USD_RATE,
            Currency.GBP: EXPECTED_GBP_RATE,
        },
    }


def test__caching_currency_exchange__returns_rate_from_cache() -> None:
    sut = CachingCurrencyExchange(cache=eur_rates(), exchange_provider=ExchangeProviderStub({}))

    assert sut.rate(Currency.EUR, Currency.USD) == EXPECTED_USD_RATE
    assert sut.rate(Currency.EUR, Currency.GBP) == EXPECTED_GBP_RATE


def test__caching_currency_exchange__when_rate_not_in_cache__pulls_from_exchange_provider() -> None:
    exchange_provider = ExchangeProviderStub(eur_rates())
    sut = CachingCurrencyExchange({}, exchange_provider)

    assert sut.rate(Currency.EUR, Currency.USD) == EXPECTED_USD_RATE
    assert sut.rate(Currency.EUR, Currency.GBP) == EXPECTED_GBP_RATE


def test__caching_currency_exchange__when_rate_not_in_cache__adds_to_cache() -> None:
    exchange_provider = ExchangeProviderStub(eur_rates())
    cache: RatesLookup = {}
    sut = CachingCurrencyExchange(cache, exchange_provider)

    sut.rate(Currency.EUR, Currency.USD)
    sut.rate(Currency.EUR, Currency.GBP)

    assert cache == eur_rates()

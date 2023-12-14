from decimal import Decimal

from coda.money import Currency, CachingCurrencyExchange


class ExchangeProviderStub:
    def __init__(self, rates: dict[Currency, dict[Currency, Decimal]]) -> None:
        self.rates = rates

    def __call__(self, currency: Currency) -> dict[Currency, Decimal]:
        return self.rates[currency]


def test__caching_currency_exchange__returns_rate_from_cache() -> None:
    expected_usd_rate = Decimal(2)
    expected_gbp_rate = Decimal(1.5)
    cache: dict[Currency, dict[Currency, Decimal]] = {
        Currency.EUR: {
            Currency.USD: expected_usd_rate,
            Currency.GBP: expected_gbp_rate,
        },
    }
    sut = CachingCurrencyExchange(cache, ExchangeProviderStub({}))

    assert sut.rate(Currency.EUR, Currency.USD) == expected_usd_rate
    assert sut.rate(Currency.EUR, Currency.GBP) == expected_gbp_rate


def test__caching_currency_exchange__when_rate_not_in_cache__pulls_from_exchange_provider() -> None:
    expected_usd_rate = Decimal(2)
    expected_gbp_rate = Decimal(1.5)
    exchange_provider = ExchangeProviderStub(
        {
            Currency.EUR: {
                Currency.USD: expected_usd_rate,
                Currency.GBP: expected_gbp_rate,
            },
        }
    )
    sut = CachingCurrencyExchange({}, exchange_provider)

    assert sut.rate(Currency.EUR, Currency.USD) == expected_usd_rate
    assert sut.rate(Currency.EUR, Currency.GBP) == expected_gbp_rate

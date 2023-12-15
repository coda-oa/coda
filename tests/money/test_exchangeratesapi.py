import json
from decimal import Decimal
from pathlib import Path

import pytest

from coda.money import Currency
from coda.money.exchangeratesapi import ExchangeRateApiJsonSchema, exchange_api


EXCHANGE_DATA_PATH = Path(__file__).parent / "exchangeapi_result.json"
EXCHANGE_DATA: ExchangeRateApiJsonSchema = json.loads(EXCHANGE_DATA_PATH.read_text())


@pytest.mark.integration
def test__can_request_rates_from_exchange_api() -> None:
    """
    We are only checking that we get valid currencies, but don't care about the rates.
    This is due to the fact that with the open API we only get access to the latest rates
    and cannot pick a specific date.
    """
    rates = exchange_api(Currency.USD)

    assert_extracted_valid_currencies(rates)


def assert_extracted_valid_currencies(rates: dict[Currency, Decimal]) -> None:
    assert all(currency.code in EXCHANGE_DATA["rates"].keys() for currency in rates)

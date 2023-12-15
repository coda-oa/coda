from decimal import Decimal
from typing import TypedDict

import httpx

from coda.money import Currency


EXCHANGERATE_API_OPEN = "https://open.er-api.com/v6/latest/{currency}"


class ExchangeRateApiJsonSchema(TypedDict):
    rates: dict[str, float]


def exchange_api(currency: Currency) -> dict[Currency, Decimal]:
    result = httpx.get(EXCHANGERATE_API_OPEN.format(currency=currency.value.code))
    result.raise_for_status()

    exchange_data: ExchangeRateApiJsonSchema = result.json()
    rates = exchange_data["rates"]
    rates = {code: rate for code, rate in rates.items() if code in Currency.allcodes()}

    return {Currency.from_code(code): Decimal(rate) for code, rate in rates.items()}

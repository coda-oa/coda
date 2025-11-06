import datetime
from decimal import Decimal

import pytest

from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import (
    CreditorId,
    FundingSourceId,
    Invoice,
    NoSuchConversion,
    Positions,
    UnassignedCosts,
)
from coda.domain.finance.invoice_positions import Position, PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, CurrencyExchange, Money
from coda.domain.publication import PublicationId
from tests.invoices.test_invoice_repository import assert_invoice_eq


def make_sut(positions: Positions) -> Invoice:
    return Invoice.new("invoice-#1234", datetime.date.today(), CreditorId(1), positions)


def position(cost: Money, tax_rate: TaxRate = TaxRate(0)) -> Position[PublicationItem]:
    return invoice_positions.create(
        item=PublicationItem(PublicationId(1), cost_type=PublicationCostType.Gold_OA),
        cost=cost,
        tax_rate=tax_rate,
    )


def test__invoice__with_no_positions__has_eur_currency() -> None:
    sut = make_sut([])

    assert sut.currency() == Currency.EUR


def test__invoice__with_positions__has_currency_of_first_position() -> None:
    first = position(Money(100, Currency.USD))
    second = position(Money(200, Currency.USD))
    sut = make_sut([first, second])

    assert sut.currency() == Currency.USD


def test__invoice__total__returns_sum_of_positions() -> None:
    first = position(Money(100, Currency.EUR))
    second = position(Money(200, Currency.EUR))
    sut = make_sut([first, second])

    assert sut.total() == Money(300, Currency.EUR)


def test__invoice__total__returns_zero_when_no_positions() -> None:
    sut = make_sut([])

    assert sut.total() == Money(0, Currency.EUR)


def test__invoice_positions_with_tax__total__returns_sum_of_positions_with_tax() -> None:
    first = position(Money(100, Currency.USD), tax_rate=TaxRate(0.07))
    second = position(Money(200, Currency.USD), tax_rate=TaxRate(0.19))
    sut = make_sut([first, second])

    assert sut.total() == Money(345, Currency.USD)
    assert sut.tax() == Money(45, Currency.USD)
    assert sut.net() == Money(300, Currency.USD)


def test__unpaid_invoice__can_add_split_position_with_unassigned_costs() -> None:
    sut = make_sut([position(Money(100, Currency.EUR))])

    p = position(Money(100, Currency.EUR))
    p.assign_funding(FundingSourceId(2), Decimal(20))

    sut.positions = [p]

    assert p in sut.positions


def test__unpaid_invoice_with_unassigned_costs__pay__raises_error() -> None:
    p = position(Money(100, Currency.EUR))
    p.assign_funding(FundingSourceId(2), Decimal(20))
    sut = make_sut([p])

    with pytest.raises(UnassignedCosts):
        sut.pay()


def test__paid_invoice__cannot_add_position_with_unassigned_costs() -> None:
    sut = make_sut([position(Money(100, Currency.EUR))])
    sut.pay()

    p = position(Money(50, Currency.EUR))
    p.assign_funding(FundingSourceId(1), Decimal(10))

    with pytest.raises(UnassignedCosts):
        sut.positions = [p]


def test__invoice_in_eur__adding_conversion__has_conversion() -> None:
    first = position(Money(100, Currency.EUR))
    second = position(Money(200, Currency.EUR))
    sut = make_sut([first, second])

    sut.add_conversion(Decimal("2.0"), Currency.JPY)
    sut.add_conversion(Decimal("3.0"), Currency.AUD)

    assert sut.conversions() == {
        Currency.JPY: Decimal("2.0"),
        Currency.AUD: Decimal("3.0"),
    }


def test__invoice_with_conversion__clear_conversions__has_no_conversions() -> None:
    first = position(Money(100, Currency.EUR))
    second = position(Money(200, Currency.EUR))
    sut = make_sut([first, second])

    sut.add_conversion(Decimal("2.0"), Currency.JPY)
    sut.add_conversion(Decimal("3.0"), Currency.AUD)

    sut.clear_conversions()

    assert sut.conversions() == {}


def in_memory_exchange(rates: dict[Currency, Decimal]) -> CurrencyExchange:
    def _exchange(origin: Currency, target: Currency) -> Decimal:
        return rates[target]

    return _exchange


def test__invoice_with_conversion__converted__returns_converted_invoice() -> None:
    exchange = in_memory_exchange({Currency.JPY: Decimal("2.0")})
    first_amount = Money(100, Currency.EUR)
    second_amount = Money(200, Currency.EUR)
    converted_first_amount = first_amount.convert_to(Currency.JPY, exchange)
    converted_second_amount = second_amount.convert_to(Currency.JPY, exchange)

    first = position(first_amount)
    second = position(second_amount)
    sut = make_sut([first, second])

    sut.add_conversion(Decimal("2.0"), Currency.JPY)
    actual = sut.convert(Currency.JPY)

    expected = Invoice.new(
        sut.number,
        sut.date,
        sut.creditor,
        [
            position(converted_first_amount),
            position(converted_second_amount),
        ],
    )
    expected.add_conversion(Decimal("0.5"), Currency.EUR)

    assert_invoice_eq(expected, actual)


def test__invoice__convert_to_same_currency__returns_self() -> None:
    first = position(Money(100, Currency.EUR))
    second = position(Money(200, Currency.EUR))
    sut = make_sut([first, second])

    actual = sut.convert(Currency.EUR)

    assert actual is sut


def test__converted_invoice__convert_back__returns_original_invoice() -> None:
    first = position(Money(100, Currency.EUR))
    second = position(Money(200, Currency.EUR))
    sut = make_sut([first, second])

    sut.add_conversion(Decimal("2.0"), Currency.JPY)
    converted = sut.convert(Currency.JPY)

    actual = converted.convert(Currency.EUR)

    assert_invoice_eq(sut, actual)


def test__converted_invoice__can_be_converted_to_same_currencies_as_original() -> None:
    first = position(Money(100, Currency.EUR))
    second = position(Money(200, Currency.EUR))

    sut = make_sut([first, second])
    sut.add_conversion(Decimal("2.0"), Currency.JPY)
    sut.add_conversion(Decimal("3.0"), Currency.AUD)

    converted_to_jpy = sut.convert(Currency.JPY)
    jpy_to_aud = converted_to_jpy.convert(Currency.AUD)

    expected = sut.convert(Currency.AUD)
    assert_invoice_eq(expected, jpy_to_aud)


def test__invoice_without_conversions__cannot_convert() -> None:
    sut = make_sut([])

    with pytest.raises(NoSuchConversion):
        sut.convert(Currency.JPY)


def test__invoice_has_currency_conversion__removing_conversion__conversion_is_deleted() -> None:
    sut = make_sut([])

    sut.add_conversion(Decimal("2.0"), Currency.JPY)
    sut.add_conversion(Decimal("3.0"), Currency.AUD)

    sut.remove_conversion(Currency.AUD)

    assert sut.conversions() == {Currency.JPY: Decimal("2.0")}


def test__invoice_has_no_currency_conversion__removing_conversion__raises_error() -> None:
    sut = make_sut([])

    with pytest.raises(NoSuchConversion):
        sut.remove_conversion(Currency.JPY)


def test__tax_rate__limits_to_four_decimal_places() -> None:
    sut = TaxRate(0.1234567)

    assert sut == TaxRate("0.1235")


def test__tax_rate__cannot_be_negative() -> None:
    with pytest.raises(ValueError):
        TaxRate(-0.1234)

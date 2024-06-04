import datetime
from collections.abc import Iterable

import pytest

from coda.invoice import CreditorId, Invoice, Position, TaxRate
from coda.money import Currency, Money
from coda.publication import PublicationId


def make_sut(positions: Iterable[Position]) -> Invoice:
    return Invoice.new("invoice-#1234", datetime.date.today(), CreditorId(1), positions)


def test__invoice__total__returns_sum_of_positions() -> None:
    first = Position(PublicationId(1), Money(100, Currency.EUR))
    second = Position(PublicationId(2), Money(200, Currency.EUR))
    sut = make_sut([first, second])

    assert sut.total() == Money(300, Currency.EUR)


def test__invoice__total__returns_zero_when_no_positions() -> None:
    sut = make_sut([])

    assert sut.total() == Money(0, Currency.EUR)


def test__invoice_positions_with_tax__total__returns_sum_of_positions_with_tax() -> None:
    first = Position(PublicationId(1), Money(100, Currency.EUR), tax_rate=TaxRate(0.07))
    second = Position(PublicationId(2), Money(200, Currency.EUR), tax_rate=TaxRate(0.19))
    sut = make_sut([first, second])

    assert sut.total() == Money(345, Currency.EUR)
    assert sut.tax() == Money(45, Currency.EUR)
    assert sut.net() == Money(300, Currency.EUR)


def test__tax_rate__limits_to_four_decimal_places() -> None:
    sut = TaxRate(0.1234567)

    assert sut == TaxRate("0.1235")


def test__tax_rate__cannot_be_negative() -> None:
    with pytest.raises(ValueError):
        TaxRate(-0.1234)

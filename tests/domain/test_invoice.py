import datetime
from collections.abc import Iterable

from coda.invoice import CreditorId, Invoice, Position
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
    first = Position(PublicationId(1), Money(100, Currency.EUR), tax_rate=0.07)
    second = Position(PublicationId(2), Money(200, Currency.EUR), tax_rate=0.19)
    sut = make_sut([first, second])

    assert sut.total() == Money(345, Currency.EUR)
    assert sut.tax() == Money(45, Currency.EUR)
    assert sut.net() == Money(300, Currency.EUR)

from collections.abc import Iterable
import datetime

import pytest

from coda.invoice import Invoice, Position, PositionNumber, PublisherId
from coda.money import Currency, Money
from coda.publication import PublicationId


def make_sut(positions: Iterable[Position]) -> Invoice:
    return Invoice.new("invoice-#1234", datetime.date.today(), PublisherId(1), positions)


def test__invoice__total__returns_sum_of_positions() -> None:
    first = Position(PositionNumber(1), PublicationId(1), Money(100, Currency.EUR))
    second = Position(PositionNumber(2), PublicationId(2), Money(200, Currency.EUR))
    sut = make_sut([first, second])

    assert sut.total() == Money(300, Currency.EUR)


def test__invoice__total__returns_zero_when_no_positions() -> None:
    sut = make_sut([])

    assert sut.total() == Money(0, Currency.EUR)


def test__invoice__positions_cannot_refer_to_publication_twice() -> None:
    first = Position(PositionNumber(1), PublicationId(1), Money(100, Currency.EUR))
    second = Position(PositionNumber(2), PublicationId(1), Money(200, Currency.EUR))

    with pytest.raises(ValueError):
        make_sut([first, second])


def test__invoice__same_position_number_twice__raises_error() -> None:
    first = Position(PositionNumber(1), PublicationId(1), Money(100, Currency.EUR))
    second = Position(PositionNumber(1), PublicationId(2), Money(200, Currency.EUR))

    with pytest.raises(ValueError):
        make_sut([first, second])

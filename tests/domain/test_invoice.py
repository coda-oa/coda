from collections.abc import Iterable

import pytest

from coda.invoice import Invoice, Position, RecipientId
from coda.money import Currency, Money
from coda.publication import PublicationId


def make_sut(positions: Iterable[Position]) -> Invoice:
    return Invoice.new(RecipientId(1), positions)


def test__invoice__total__returns_sum_of_positions() -> None:
    first = Position.new(PublicationId(1), Money(100, Currency.EUR))
    second = Position.new(PublicationId(2), Money(200, Currency.EUR))
    sut = make_sut([first, second])

    assert sut.total() == Money(300, Currency.EUR)


def test__invoice__total__returns_zero_when_no_positions() -> None:
    sut = make_sut([])

    assert sut.total() == Money(0, Currency.EUR)


def test__invoice__positions_cannot_refer_to_publication_twice() -> None:
    first = Position.new(PublicationId(1), Money(100, Currency.EUR))
    second = Position.new(PublicationId(1), Money(200, Currency.EUR))

    with pytest.raises(ValueError):
        make_sut([first, second])

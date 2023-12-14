from decimal import Decimal
from operator import eq, ne, lt, le, gt, ge
from typing import Callable

import pytest

from coda.money import Currency, Money


@pytest.mark.parametrize("value", [100, "100", "100.0", Decimal(100)])
def test__money_inits_are_equivalent(value: int | str | Decimal) -> None:
    money = Money(value, Currency.EUR)
    assert money == money
    assert money == Money(100, Currency.EUR)


def test__money__when_converted_to_same_currency__returns_same_money() -> None:
    money = Money(100, Currency.EUR)

    result = money.convert_to(Currency.EUR, lambda origin, target: Decimal(1))

    assert result == money


def test__money__when_converted_to_different_currency__returns_converted_money() -> None:
    money = Money(100, Currency.EUR)

    result = money.convert_to(Currency.USD, lambda origin, target: Decimal(2))

    assert result == Money(200, Currency.USD)


def test__money_cannot_be_compared_to_non_money() -> None:
    with pytest.raises(TypeError):
        _ = Money(100, Currency.EUR) == 100


@pytest.mark.parametrize("compare", [eq, ne, lt, le, gt, ge])
def test__money_in_different_currencies_cannot_be_compared(
    compare: Callable[[object, object], bool]
) -> None:
    with pytest.raises(TypeError):
        _ = compare(Money(100, Currency.EUR), Money(100, Currency.USD))


def test__unequal_money_is_not_equal() -> None:
    assert Money(100, Currency.EUR) != Money(99, Currency.EUR)


def test__more_money_is_greater() -> None:
    assert Money(100, Currency.EUR) > Money(99, Currency.EUR)


def test__less_money_is_less() -> None:
    assert Money(99, Currency.EUR) < Money(100, Currency.EUR)


def test__less_or_same_money_is_less_or_equal() -> None:
    assert Money(99, Currency.EUR) <= Money(100, Currency.EUR)
    assert Money(100, Currency.EUR) <= Money(100, Currency.EUR)


def test__more_or_same_money_is_more_or_equal() -> None:
    assert Money(100, Currency.EUR) >= Money(99, Currency.EUR)
    assert Money(100, Currency.EUR) >= Money(100, Currency.EUR)

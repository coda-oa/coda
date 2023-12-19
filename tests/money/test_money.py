from collections.abc import Callable
from decimal import Decimal
from operator import eq, ge, gt, le, lt, ne

import pytest

from coda.money import Currency, Money
from tests.checks.test_costlimit import one2one


@pytest.mark.parametrize("value", [100, "100", "100.0", Decimal(100)])
def test__money_inits_are_equivalent(value: int | str | Decimal) -> None:
    money = Money(value, Currency.EUR)
    assert money == money
    assert money == Money(100, Currency.EUR)


def test__creating_money_with_more_minor_units_than_currency__uses_half_round_up() -> None:
    assert Money("100.004", Currency.EUR) == Money("100.00", Currency.EUR)
    assert Money("100.005", Currency.EUR) == Money("100.01", Currency.EUR)


def test__money__when_converted_to_same_currency__returns_same_money() -> None:
    money = Money(100, Currency.EUR)

    result = money.convert_to(Currency.EUR, lambda origin, target: Decimal(1))

    assert result == money


def test__money__when_converted_to_different_currency__returns_converted_money() -> None:
    money = Money(100, Currency.EUR)

    result = money.convert_to(Currency.USD, lambda origin, target: Decimal(2))

    assert result == Money(200, Currency.USD)


@pytest.mark.parametrize(["origin", "expected"], [("1.005", "1.01"), ("1.004", "1.00")])
def test__money_with_3_minor_units__when_converted_to_2_minor_units__converts_with_half_round_up(
    origin: str, expected: str
) -> None:
    money = Money(origin, Currency.JOD)

    actual = money.convert_to(Currency.EUR, one2one)

    assert actual == Money(expected, Currency.EUR)


def test__money_with_2_minor_units__when_converted_to_0_minor_units__converts_with_half_round_up() -> (
    None
):
    money = Money("1.50", Currency.EUR)

    actual = money.convert_to(Currency.JPY, one2one)

    assert actual == Money("2.00", Currency.JPY)


def test__money_cannot_be_compared_to_non_money() -> None:
    with pytest.raises(TypeError):
        _ = Money(100, Currency.EUR) == 100


@pytest.mark.parametrize("compare", [eq, ne, lt, le, gt, ge])
def test__money_in_different_currencies_cannot_be_compared(
    compare: Callable[[object, object], bool]
) -> None:
    with pytest.raises(TypeError):
        _ = compare(Money(100, Currency.EUR), Money(100, Currency.USD))


def test__zero_money_in_different_currencies_is_equal() -> None:
    assert Money(0, Currency.EUR) == Money(0, Currency.USD)


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

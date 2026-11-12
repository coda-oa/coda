from decimal import Decimal

import pytest

from coda.contexts.statistics.measures import gross_assignment, gross_of
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money

NINETEEN = TaxRate.from_percentage(19)


def test__gross_of_regular_position__adds_tax_to_the_net_cost() -> None:
    gross = gross_of(Money("100.00", Currency.EUR), NINETEEN, is_vat=False)

    assert gross == Money("119.00", Currency.EUR)


def test__gross_of_regular_position__rounds_half_up_to_currency_minor_units() -> None:
    gross = gross_of(Money("10.42", Currency.EUR), TaxRate.from_percentage(7), is_vat=False)

    assert gross == Money("11.15", Currency.EUR)


def test__gross_of_vat_position__is_the_amount_itself() -> None:
    gross = gross_of(Money("19.00", Currency.EUR), NINETEEN, is_vat=True)

    assert gross == Money("19.00", Currency.EUR)


@pytest.mark.parametrize(
    ["amount", "expected"],
    [(Decimal("100.00"), "119.00"), (Decimal("0.00"), "0.00"), (Decimal("33.33"), "39.66")],
)
def test__gross_assignment_regular__adds_the_positions_tax_rate_to_the_net_amount(
    amount: Decimal, expected: str
) -> None:
    gross = gross_assignment(amount, NINETEEN, Currency.EUR, is_vat=False)

    assert gross == Money(expected, Currency.EUR)


def test__gross_assignment_vat_position__leaves_the_amount_unchanged() -> None:
    gross = gross_assignment(Decimal("19.00"), NINETEEN, Currency.EUR, is_vat=True)

    assert gross == Money("19.00", Currency.EUR)

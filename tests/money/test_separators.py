from decimal import Decimal

import pytest

from coda.domain.money import DecimalSeparator


def test__decimal_separator__render__english_is_the_identity() -> None:
    value = Decimal("1600.0000")

    assert DecimalSeparator.English.render(value) == "1600.0000"
    assert DecimalSeparator.English.render("1.5") == "1.5"
    assert DecimalSeparator.English.render(1.5) == "1.5"


def test__decimal_separator__render__german_swaps_dot_for_comma() -> None:
    assert DecimalSeparator.German.render(Decimal("1600.0000")) == "1600,0000"
    assert DecimalSeparator.German.render("1250.00") == "1250,00"
    assert DecimalSeparator.German.render(1.5) == "1,5"


@pytest.mark.parametrize("separator", list(DecimalSeparator))
def test__decimal_separator__render__none_passes_through(separator: DecimalSeparator) -> None:
    """Blank comparison cells stay blank, for every locale."""
    assert separator.render(None) is None

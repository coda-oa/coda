import datetime

import pytest

from coda.domain.date import DateRange, InvalidDateError, InvalidDateRangeError


@pytest.mark.parametrize("value", ["not-a-date", "2024-13-01", "01-01-2024", "2024-01"])
def test__from_iso__malformed_start__raises_invalid_date_error(value: str) -> None:
    with pytest.raises(InvalidDateError, match="is not a valid date"):
        DateRange.from_iso(start=value, end="2024-12-31")


def test__from_iso__inverted__raises_invalid_date_range_error() -> None:
    with pytest.raises(InvalidDateRangeError, match="must be before end date"):
        DateRange.from_iso(start="2025-01-01", end="2024-01-01")


def test__from_iso__half_open__defaults_the_missing_side() -> None:
    assert DateRange.from_iso(start="2024-01-01") == DateRange(
        datetime.date(2024, 1, 1), datetime.date.max
    )


def test__inverted_range__still_raises_a_value_error_for_existing_handlers() -> None:
    """contracts/forms.py catches ValueError around DateRange construction."""
    with pytest.raises(ValueError):
        DateRange(datetime.date(2025, 1, 1), datetime.date(2024, 1, 1))


def test__prior_window__bounded_range__is_the_same_length_immediately_before() -> None:
    period = DateRange(datetime.date(2026, 3, 10), datetime.date(2026, 4, 20))

    prior = period.prior_window()

    assert prior is not None
    assert (prior.start, prior.end) == (datetime.date(2026, 1, 27), datetime.date(2026, 3, 9))
    assert (prior.end - prior.start).days == (period.end - period.start).days


def test__prior_window__one_day_range__is_the_previous_day() -> None:
    period = DateRange(datetime.date(2026, 5, 1), datetime.date(2026, 5, 1))

    prior = period.prior_window()

    assert prior == DateRange(datetime.date(2026, 4, 30), datetime.date(2026, 4, 30))


def test__prior_window__unbounded_or_half_open__is_none() -> None:
    """A missing bound uses the date.min/max sentinels; "the same length
    before eternity" is not a window, so compare stays off."""
    assert DateRange(datetime.date.min, datetime.date.max).prior_window() is None
    assert DateRange(datetime.date(2026, 1, 1), datetime.date.max).prior_window() is None
    assert DateRange(datetime.date.min, datetime.date(2026, 12, 31)).prior_window() is None

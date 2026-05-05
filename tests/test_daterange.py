from datetime import date

import pytest

from coda.domain.date import DateRange


def test__cannot_create_date_range_with_start_after_end() -> None:
    with pytest.raises(ValueError):
        DateRange(
            start=date(2026, 1, 1),
            end=date(2025, 1, 1),
        )

    with pytest.raises(ValueError):
        DateRange.create(
            start=date(2026, 1, 1),
            end=date(2025, 1, 1),
        )


def test__date_range_contains_date_between_start_and_end() -> None:
    sut = DateRange(date(2024, 1, 1), date(2025, 1, 1))

    assert date(2024, 1, 1) in sut
    assert date(2024, 8, 16) in sut
    assert date(2025, 1, 1) in sut
    assert date(2023, 12, 31) not in sut
    assert date(2025, 1, 2) not in sut

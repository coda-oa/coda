import datetime
from dataclasses import dataclass
from typing import Self

from coda.domain.errors import DomainError


class InvalidDateError(DomainError):
    """A value could not be read as a YYYY-MM-DD calendar date."""

    @classmethod
    def invalid(cls, value: str) -> Self:
        return cls(f"'{value}' is not a valid date (YYYY-MM-DD).")


class InvalidDateRangeError(DomainError):
    """The range's start falls after its end."""

    def __init__(self, start: datetime.date, end: datetime.date) -> None:
        super().__init__(f"Start date {start} must be before end date {end}")
        self.start = start
        self.end = end


def _parse_iso(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise InvalidDateError.invalid(value) from error


@dataclass(frozen=True, slots=True)
class DateRange:
    start: datetime.date
    end: datetime.date

    @classmethod
    def create(
        cls, *, start: datetime.date | None = None, end: datetime.date | None = None
    ) -> Self:
        start_date = start or datetime.date.min
        end_date = end or datetime.date.max

        return cls(start_date, end_date)

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise InvalidDateRangeError(self.start, self.end)

    @classmethod
    def year(cls, year: int) -> Self:
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        return cls(year_start, year_end)

    @classmethod
    def from_iso(cls, *, start: str | None = None, end: str | None = None) -> Self:
        """Build a range from raw YYYY-MM-DD strings, reporting each problem as a domain error."""
        return cls(
            _parse_iso(start) if start else datetime.date.min,
            _parse_iso(end) if end else datetime.date.max,
        )

    def is_unbounded(self) -> bool:
        return self.start == datetime.date.min and self.end == datetime.date.max

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, datetime.date):
            return False

        return self.start <= key <= self.end

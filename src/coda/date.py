import datetime
from typing import NamedTuple, Self


class DateRange(NamedTuple):
    start: datetime.date
    end: datetime.date

    @classmethod
    def create(
        cls, *, start: datetime.date | None = None, end: datetime.date | None = None
    ) -> Self:
        start_date = start or datetime.date.min
        end_date = end or datetime.date.max
        if start_date > end_date:
            raise ValueError(f"Start date {start_date} must be before end date {end_date}")

        return cls(start_date, end_date)

    @classmethod
    def year(cls, year: int) -> Self:
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        return cls(year_start, year_end)

    @classmethod
    def try_fromisoformat(cls, *, start: str | None = None, end: str | None = None) -> Self:
        start_date = datetime.date.fromisoformat(start) if start else datetime.date.min
        end_date = datetime.date.fromisoformat(end) if end else datetime.date.max
        return cls(start_date, end_date)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, datetime.date):
            return False

        return self.start <= key <= self.end

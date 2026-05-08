import datetime
from dataclasses import dataclass
from typing import Self


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
            raise ValueError(f"Start date {self.start} must be before end date {self.end}")

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

    def is_unbounded(self) -> bool:
        return self.start == datetime.date.min and self.end == datetime.date.max

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, datetime.date):
            return False

        return self.start <= key <= self.end

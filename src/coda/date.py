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
        return cls(start_date, end_date)

    @classmethod
    def try_fromisoformat(cls, *, start: str | None = None, end: str | None = None) -> Self:
        start_date = datetime.date.fromisoformat(start) if start else datetime.date.min
        end_date = datetime.date.fromisoformat(end) if end else datetime.date.max
        return cls(start_date, end_date)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, datetime.date):
            return False

        return self.start <= key <= self.end

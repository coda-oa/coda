import datetime
from collections.abc import Iterable
from typing import NamedTuple, NewType

from coda.date import DateRange
from coda.publication import JournalId
from coda.string import NonEmptyStr

ContractId = NewType("ContractId", int)
PublisherId = NewType("PublisherId", int)


class Contract(NamedTuple):
    id: ContractId | None
    name: NonEmptyStr
    publishers: tuple[PublisherId, ...]
    period: DateRange = DateRange.create()
    journals: tuple[JournalId, ...] = ()

    @classmethod
    def new(
        cls,
        name: NonEmptyStr,
        publishers: Iterable[PublisherId],
        period: DateRange = DateRange.create(),
        journals: Iterable[JournalId] = (),
    ) -> "Contract":
        return cls(None, name, tuple(publishers), period, tuple(journals))

    def is_active(self, date: datetime.date | None = None) -> bool:
        date = date or datetime.date.today()
        return date in self.period

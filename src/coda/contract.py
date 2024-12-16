from dataclasses import dataclass
import datetime
from collections.abc import Iterable
from typing import TYPE_CHECKING, NewType

from coda.date import DateRange
from coda.string import NonEmptyStr


if TYPE_CHECKING:
    from coda.publication import JournalId


class ContractId(int):
    __slots__ = ()


PublisherId = NewType("PublisherId", int)


@dataclass(slots=True)
class Contract:
    id: ContractId | None
    name: NonEmptyStr
    publishers: tuple[PublisherId, ...]
    period: DateRange = DateRange.create()
    journals: tuple["JournalId", ...] = ()

    @classmethod
    def new(
        cls,
        name: NonEmptyStr,
        publishers: Iterable[PublisherId],
        period: DateRange = DateRange.create(),
        journals: Iterable["JournalId"] = (),
    ) -> "Contract":
        return cls(None, name, tuple(publishers), period, tuple(journals))

    def is_active(self, date: datetime.date | None = None) -> bool:
        date = date or datetime.date.today()
        return date in self.period


@dataclass(slots=True)
class ContractYear:
    """
    A contract year is a year within the period of a contract.
    The contract year can even refer to a year where the contract is only partially active.
    """

    year: int
    contract: Contract

    def __post_init__(self) -> None:
        if self.year not in self._contract_years():
            raise ValueError(f"Contract is not active in {self.year}")

    def _contract_years(self) -> range:
        return range(self.contract.period.start.year, self.contract.period.end.year + 1)

    def __str__(self) -> str:
        return f"{self.contract.name} ({self.year})"

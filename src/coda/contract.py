import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NewType

from coda.date import DateRange
from coda.string import NonEmptyStr

if TYPE_CHECKING:
    from coda.publication import JournalId


class ContractId(int):
    __slots__ = ()


PublisherId = NewType("PublisherId", int)


class PublicationBilling(enum.StrEnum):
    Individually = enum.auto()
    Consolidated = enum.auto()


@dataclass(slots=True)
class Contract:
    id: ContractId | None
    name: NonEmptyStr
    publishers: Iterable[PublisherId]
    period: DateRange = DateRange.create()
    journals: Iterable["JournalId"] = ()
    publication_billing: PublicationBilling = PublicationBilling.Individually

    @classmethod
    def new(
        cls,
        name: NonEmptyStr,
        publishers: Iterable[PublisherId] = (),
        period: DateRange = DateRange.create(),
        journals: Iterable["JournalId"] = (),
        publication_billing: PublicationBilling = PublicationBilling.Individually,
    ) -> "Contract":
        return cls(None, name, publishers, period, journals, publication_billing)

    def uses_consolidated_billing(self) -> bool:
        return self.publication_billing == PublicationBilling.Consolidated

    def is_active(self, date: datetime.date | None = None) -> bool:
        date = date or datetime.date.today()
        return date in self.period

    def is_active_in_year(self, year: int) -> bool:
        return year in range(self.period.start.year, self.period.end.year + 1)

    def in_year(self, year: int) -> "ContractYear":
        return ContractYear(year, self)

    def in_year_or_first(self, year: int) -> "ContractYear":
        if self.is_active_in_year(year):
            return self.in_year(year)

        return self.in_first_year()

    def in_first_year(self) -> "ContractYear":
        return ContractYear(self.period.start.year, self)


@dataclass(slots=True)
class ContractYear:
    """
    A contract year is a year within the period of a contract.
    The contract year can even refer to a year where the contract is only partially active.
    """

    year: int
    contract: Contract

    def __post_init__(self) -> None:
        if not self.contract.is_active_in_year(self.year):
            raise InvalidContractYearError(self.year, self.contract)

    def _contract_years(self) -> range:
        return range(self.contract.period.start.year, self.contract.period.end.year + 1)

    def uses_consolidated_billing(self) -> bool:
        return self.contract.uses_consolidated_billing()

    @property
    def id(self) -> ContractId | None:
        return self.contract.id

    @property
    def contract_id(self) -> ContractId | None:
        return self.contract.id

    @property
    def name(self) -> str:
        return self.contract.name

    @property
    def publishers(self) -> Iterable[PublisherId]:
        return self.contract.publishers

    @property
    def journals(self) -> Iterable["JournalId"]:
        return self.contract.journals

    def __str__(self) -> str:
        return f"{self.contract.name} ({self.year})"

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, ContractYear):
            return False

        return self.year == value.year and self.contract_id == value.contract_id

    def __hash__(self) -> int:
        return hash((str(self.__class__), self.year, self.contract_id))


class InvalidContractYearError(ValueError):
    def __init__(self, year: int, contract: Contract, *args: object) -> None:
        super().__init__(f"Contract is not active in {year}", *args)
        self.year = year
        self.contract = contract

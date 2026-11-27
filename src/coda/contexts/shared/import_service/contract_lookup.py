import datetime
from collections.abc import Iterable
from typing import Protocol

from coda.apps.contracts import repository as contract_repository
from coda.domain.contract import Contract
from coda.domain.date import DateRange
from coda.domain.string import NonEmptyStr


class ContractReference(Protocol):
    name: str
    year: int


def contract_periods(contracts: Iterable[ContractReference]) -> dict[str, DateRange]:
    """Compute the full-year period per contract name from all references."""
    periods: dict[str, tuple[int, int]] = {}
    for contract in contracts:
        low, high = periods.get(contract.name, (contract.year, contract.year))
        periods[contract.name] = (min(contract.year, low), max(contract.year, high))

    return {
        name: DateRange.create(
            start=datetime.date(low, 1, 1),
            end=datetime.date(high, 12, 31),
        )
        for name, (low, high) in periods.items()
    }


def find_contracts(names: Iterable[str]) -> dict[str, Contract]:
    """Resolve existing contracts by name; the first match wins."""
    lookup: dict[str, Contract] = {}
    for contract in contract_repository.find_all_by_names(names):
        lookup.setdefault(str(contract.name), contract)

    return lookup


def fetch_or_create_contracts(contracts: Iterable[ContractReference]) -> dict[str, Contract]:
    """Fetch existing contracts and create missing ones, returning a name lookup."""
    contracts = list(contracts)
    if not contracts:
        return {}

    periods = contract_periods(contracts)
    lookup = find_contracts(periods)
    missing = [
        Contract.new(name=NonEmptyStr(name), period=period)
        for name, period in periods.items()
        if name not in lookup
    ]
    for created in contract_repository.create_many(missing):
        lookup[str(created.name)] = created

    return lookup

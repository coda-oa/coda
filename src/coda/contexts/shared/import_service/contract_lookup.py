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


def fetch_or_create_contracts(contracts: Iterable[ContractReference]) -> dict[str, Contract]:
    """
    Fetches all existing contracts by name and creates any that are missing.
    Returns a mapping of contract name to Contract domain object.

    Note: The input contracts iterable is eagerly realized as a list to avoid
    generator exhaustion in cases where the input is a generator. Multiple passes
    over this collection are required, so collection is necessary.
    """
    contracts = list(contracts)
    if not contracts:
        return {}

    contract_names = {c.name for c in contracts}

    contract_periods: dict[str, tuple[int, int]] = {}
    for c in contracts:
        if c.name not in contract_periods:
            contract_periods[c.name] = (c.year, c.year)
        else:
            current = contract_periods[c.name]
            contract_periods[c.name] = (min(c.year, current[0]), max(c.year, current[1]))

    existing_contracts = contract_repository.find_all_by_names(contract_names)

    lookup: dict[str, Contract] = {}
    for domain_obj in existing_contracts:
        name_str = str(domain_obj.name)
        if name_str not in lookup:
            lookup[name_str] = domain_obj

    missing_names = contract_names - set(lookup.keys())

    if missing_names:
        new_contracts = [
            Contract.new(
                name=NonEmptyStr(name),
                period=DateRange.create(
                    start=datetime.date(contract_periods[name][0], 1, 1),
                    end=datetime.date(contract_periods[name][1], 12, 31),
                ),
            )
            for name in missing_names
        ]
        created_contracts = contract_repository.create_many(new_contracts)
        for contract in created_contracts:
            name_str = str(contract.name)
            lookup[name_str] = contract

    return lookup

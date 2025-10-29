import datetime

import pytest

from coda.domain.contract import Contract, ContractYear, PublisherId
from coda.domain.date import DateRange
from coda.coda_itertools import LazyCachedIterable
from coda.domain.string import NonEmptyStr


def test__contract_year__cannot_create_outside_active_contract_period() -> None:
    with pytest.raises(ValueError):
        previous_year = 2023
        make_contract().in_year(previous_year)

    with pytest.raises(ValueError):
        next_year = 2025
        make_contract().in_year(next_year)


def test__contract_active_from_mid_year__can_create_contract_year() -> None:
    contract = make_contract(
        period=DateRange.create(start=datetime.date(2024, 6, 1), end=datetime.date(2024, 12, 31))
    )

    contract_year = contract.in_year(year=2024)
    assert contract_year.year == 2024
    assert contract_year.contract == contract


def test__contract_year__equals_contract_year_with_same_year_and_contract() -> None:
    contract_ref = make_contract()
    contract_year = ContractYear(year=2024, contract=contract_ref)

    other_contact_ref = make_contract()
    other_contract_year = ContractYear(year=2024, contract=other_contact_ref)

    assert contract_year == other_contract_year


def make_contract(
    period: DateRange = DateRange.create(
        start=datetime.date(2024, 1, 1), end=datetime.date(2024, 12, 31)
    ),
) -> Contract:
    return Contract.new(
        name=NonEmptyStr("contract name"),
        period=period,
        # NOTE: we are intentionally using an iterable that pytest cannot compare natively
        # to ensure that contract year comparison cannot just compare references
        publishers=LazyCachedIterable(pid for pid in (PublisherId(1), PublisherId(2))),
    )

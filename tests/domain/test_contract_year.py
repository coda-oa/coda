import datetime

import pytest

from coda.contract import Contract, ContractYear
from coda.date import DateRange
from coda.string import NonEmptyStr


def test__contract_year__cannot_create_outside_active_contract_period() -> None:
    with pytest.raises(ValueError):
        previous_year = 2023
        ContractYear(year=previous_year, contract=make_contract())

    with pytest.raises(ValueError):
        next_year = 2025
        ContractYear(year=next_year, contract=make_contract())


def test__contract_active_from_mid_year__can_create_contract_year() -> None:
    contract = make_contract(
        period=DateRange.create(start=datetime.date(2024, 6, 1), end=datetime.date(2024, 12, 31))
    )

    contract_year = ContractYear(year=2024, contract=contract)
    assert contract_year.year == 2024
    assert contract_year.contract == contract


def make_contract(
    period: DateRange = DateRange.create(
        start=datetime.date(2024, 1, 1), end=datetime.date(2024, 12, 31)
    )
) -> Contract:
    return Contract.new(name=NonEmptyStr("contract name"), period=period, publishers=())

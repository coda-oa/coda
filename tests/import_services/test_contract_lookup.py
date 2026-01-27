from dataclasses import dataclass
from datetime import date

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.contexts.shared.import_service.contract_lookup import fetch_or_create_contracts
from coda.domain.date import DateRange
from tests import domainfactory
from tests.contracts.test_contract_repository import assert_contract_eq


@dataclass
class ContractReference:
    name: str
    year: int


@pytest.mark.django_db
def test__contract_lookup__creates_contracts_within_given_contract_years() -> None:
    expected = domainfactory.contract(
        period=DateRange.create(
            start=date(1990, 1, 1),
            end=date(2026, 12, 31),
        ),
    )

    actual = fetch_or_create_contracts(
        [
            ContractReference(expected.name, 1994),
            ContractReference(expected.name, 2026),
            ContractReference(expected.name, 2001),
            ContractReference(expected.name, 1990),
        ]
    )

    assert_contract_eq(actual[expected.name], expected)


@pytest.mark.django_db
def test__contract_lookup__existing_contracts_stay_unchanged() -> None:
    expected = domainfactory.contract(
        period=DateRange.create(
            start=date(1990, 1, 1),
            end=date(2026, 12, 31),
        ),
    )
    expected.id = contract_repository.create(expected)

    actual = fetch_or_create_contracts(
        [
            ContractReference(expected.name, 1989),
            ContractReference(expected.name, 2027),
        ]
    )

    assert_contract_eq(actual[expected.name], expected)

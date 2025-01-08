import datetime

import pytest

from coda.apps.contracts.services import get_by_id, save
from coda.contract import Contract, PublisherId
from coda.date import DateRange
from coda.publication import JournalId
from coda.string import NonEmptyStr
from tests import modelfactory

START_DATE = datetime.date(2024, 1, 1)
END_DATE = datetime.date(2024, 12, 31)
INSIDE_DATE_RANGE = datetime.date(2024, 6, 1)
CONTRACT_NAME = NonEmptyStr("Test Contract")


@pytest.mark.django_db
def test__can_create_contract() -> None:
    publishers_ids = make_publishers()
    journal_ids = make_journals(publishers_ids)

    expected = Contract.new(CONTRACT_NAME, publishers_ids, date_range(), journal_ids)

    contract_id = save(expected)

    actual = get_by_id(contract_id)
    assert_contract_eq(actual, expected)


@pytest.mark.django_db
def test__given_saved_contract__save_udpated__updates_contract() -> None:
    publishers_ids = make_publishers()
    journal_ids = make_journals(publishers_ids)

    contract = Contract.new(CONTRACT_NAME, publishers_ids, date_range(), journal_ids)
    contract_id = save(contract)

    expected = get_by_id(contract_id)
    expected.name = NonEmptyStr("Updated")
    expected.publishers = ()
    expected.journals = ()

    save(expected)

    actual = get_by_id(contract_id)
    assert contract_id == actual.id
    assert_contract_eq(actual, expected)


def make_contract(publishers: list[PublisherId], journals: list[JournalId]) -> Contract:
    return Contract.new(CONTRACT_NAME, publishers, date_range(), journals)


def make_publishers() -> list[PublisherId]:
    return [PublisherId(modelfactory.publisher().pk) for _ in range(2)]


def make_journals(publishers_ids: list[PublisherId]) -> list[JournalId]:
    return [JournalId(modelfactory.journal(publisher_id).pk) for publisher_id in publishers_ids]


def assert_contract_eq(actual: Contract, expected: Contract) -> None:
    assert actual.name == expected.name
    assert actual.publishers == expected.publishers
    assert actual.period == expected.period
    assert actual.journals == expected.journals


def date_range() -> DateRange:
    return DateRange.create(start=START_DATE, end=END_DATE)

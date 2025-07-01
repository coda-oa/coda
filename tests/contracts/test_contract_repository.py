import datetime
import random

import pytest

from coda.apps.contracts.repository import create, get_by_id, update
from coda.domain.contract import Contract, PublicationBilling, PublisherId
from coda.domain.date import DateRange
from coda.domain.publication import JournalId
from coda.domain.string import NonEmptyStr
from tests import modelfactory

START_DATE = datetime.date(2024, 1, 1)
END_DATE = datetime.date(2024, 12, 31)
INSIDE_DATE_RANGE = datetime.date(2024, 6, 1)
CONTRACT_NAME = NonEmptyStr("Test Contract")


@pytest.mark.django_db
def test__can_create_contract() -> None:
    publishers_ids = make_publishers()
    journal_ids = make_journals(publishers_ids)

    expected = Contract.new(
        CONTRACT_NAME, publishers_ids, date_range(), journal_ids, PublicationBilling.Consolidated
    )

    contract_id = create(expected)

    actual = get_by_id(contract_id)
    assert_contract_eq(actual, expected)


@pytest.mark.django_db
def test__given_saved_contract__create_again__raises_error() -> None:
    sut = Contract.new(NonEmptyStr("Contract"))
    sut.id = create(sut)

    with pytest.raises(ValueError):
        create(sut)


@pytest.mark.django_db
def test__given_saved_contract__update__updates_contract() -> None:
    publishers_ids = make_publishers()
    journal_ids = make_journals(publishers_ids)

    contract = Contract.new(CONTRACT_NAME, publishers_ids, date_range(), journal_ids)
    contract_id = create(contract)

    expected = get_by_id(contract_id)
    expected.name = NonEmptyStr("Updated")
    expected.publishers = ()
    expected.journals = ()
    expected.publication_billing = PublicationBilling.Consolidated

    update(expected)

    actual = get_by_id(contract_id)
    assert contract_id == actual.id
    assert_contract_eq(actual, expected)


@pytest.mark.django_db
def test__given_unsaved_contract__update__raises_error() -> None:
    sut = Contract.new(NonEmptyStr("Contract"))

    with pytest.raises(ValueError):
        update(sut)


def make_contract(publishers: list[PublisherId], journals: list[JournalId]) -> Contract:
    billing = random.choice([billing_type for billing_type in PublicationBilling])
    return Contract.new(CONTRACT_NAME, publishers, date_range(), journals, billing)


def make_publishers() -> list[PublisherId]:
    return [PublisherId(modelfactory.publisher().pk) for _ in range(2)]


def make_journals(publishers_ids: list[PublisherId]) -> list[JournalId]:
    return [JournalId(modelfactory.journal(publisher_id).pk) for publisher_id in publishers_ids]


def assert_contract_eq(actual: Contract, expected: Contract) -> None:
    assert actual.name == expected.name
    assert actual.period == expected.period
    assert set(actual.publishers) == set(expected.publishers)
    assert set(actual.journals) == set(expected.journals)
    assert actual.publication_billing == expected.publication_billing


def date_range() -> DateRange:
    return DateRange.create(start=START_DATE, end=END_DATE)

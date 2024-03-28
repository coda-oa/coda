import datetime

import pytest
from django.test import Client

from coda.apps.contracts.models import Contract
from coda.apps.contracts.services import DateRange, contract_create
from coda.apps.publishers.models import Publisher

START_DATE = datetime.date(2024, 1, 1)
END_DATE = datetime.date(2024, 12, 31)

INSIDE_DATE_RANGE = datetime.date(2024, 6, 1)
AFTER_END_DATE = datetime.date(2025, 6, 1)
BEFORE_START_DATE = datetime.date(2023, 6, 1)

CONTRACT_NAME = "Test Contract"


def inside_date_range() -> DateRange:
    return DateRange(start_date=START_DATE, end_date=END_DATE)


def outside_date_range() -> DateRange:
    return DateRange(start_date=START_DATE, end_date=END_DATE)


def only_start_date() -> DateRange:
    return DateRange(start_date=START_DATE)


def only_end_date() -> DateRange:
    return DateRange(end_date=END_DATE)


def no_dates() -> "DateRange":
    return DateRange(start_date=None, end_date=None)


@pytest.mark.django_db
def test__can_create_contract() -> None:
    publishers = make_publishers()
    now = INSIDE_DATE_RANGE
    contract_create(CONTRACT_NAME, publishers, inside_date_range())

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, inside_date_range())
    assert actual.is_active(now) is True


@pytest.mark.django_db
def test__contract_create__can_create_contract_without_dates() -> None:
    publishers = make_publishers()

    contract_create(CONTRACT_NAME, publishers)

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, no_dates())
    assert actual.is_active() is True


@pytest.mark.django_db
def test__contract_create__today_outside_date_range__contract_is_inactive() -> None:
    publishers = make_publishers()

    contract_create(CONTRACT_NAME, publishers, outside_date_range())

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, outside_date_range())
    assert actual.is_active(AFTER_END_DATE) is False


@pytest.mark.django_db
def test__created_contract_in_date_range__now_outside_date_range__contract_is_inactive() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers, inside_date_range())

    now = AFTER_END_DATE
    active = sut.is_active(now)

    assert active is False


@pytest.mark.django_db
def test__contract_create__only_start_date__now_after_start__contract_is_active() -> None:
    publishers = make_publishers()
    dates = only_start_date()

    contract_create(CONTRACT_NAME, publishers, dates)

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, dates)
    assert actual.is_active(AFTER_END_DATE) is True


@pytest.mark.django_db
def test__contract_create__only_start_date__now_before_start__contract_is_not_active() -> None:
    publishers = make_publishers()
    dates = only_start_date()

    contract_create(CONTRACT_NAME, publishers, dates)

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, dates)
    assert actual.is_active(BEFORE_START_DATE) is False


@pytest.mark.django_db
def test__contract_create__only_end_date__now_before_end__contract_is_active() -> None:
    publishers = make_publishers()
    dates = only_end_date()

    contract_create(CONTRACT_NAME, publishers, dates)

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, dates)
    assert actual.is_active(BEFORE_START_DATE) is True


@pytest.mark.django_db
def test__contract_create__only_end_date_before_now__contract_is_not_active() -> None:
    publishers = make_publishers()
    dates = only_end_date()

    contract_create(CONTRACT_NAME, publishers, dates)

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, dates)
    assert actual.is_active(AFTER_END_DATE) is False


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_contract_view__can_create_contract(client: Client) -> None:
    publishers = make_publishers()

    client.post(
        "/contracts/create/",
        data={
            "name": CONTRACT_NAME,
            "publishers": [publisher.pk for publisher in publishers],
            "start_date": START_DATE,
            "end_date": END_DATE,
        },
    )

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, inside_date_range())
    assert actual.is_active(INSIDE_DATE_RANGE) is True


def assert_contract_equals(
    contract: Contract, publishers: list[Publisher], date_range: DateRange | None = None
) -> None:
    date_range = date_range or no_dates()
    assert contract.name == CONTRACT_NAME
    assert list(contract.publishers.all()) == publishers
    assert contract.start_date == date_range.start_date
    assert contract.end_date == date_range.end_date


def make_publishers() -> list[Publisher]:
    return Publisher.objects.bulk_create(
        [Publisher(name="Publisher 1"), Publisher(name="Publisher 2")]
    )

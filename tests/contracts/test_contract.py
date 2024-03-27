import datetime
from django.test import Client
import pytest
from coda.apps.contracts.models import Contract
from coda.apps.contracts.services import contract_create
from coda.apps.publishers.models import Publisher

START_DATE = datetime.date(2024, 1, 1)
END_DATE = datetime.date(2024, 12, 31)

INSIDE_DATE_RANGE = datetime.date(2024, 6, 1)
AFTER_END_DATE = datetime.date(2025, 6, 1)
BEFORE_START_DATE = datetime.date(2023, 6, 1)


@pytest.mark.django_db
def test__can_create_contract() -> None:
    name = "Test Contract"
    publishers = make_publishers()
    contract_create(name, publishers, START_DATE, END_DATE, now=INSIDE_DATE_RANGE)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(actual, name, publishers, is_active=True)


@pytest.mark.django_db
def test__contract_create__can_create_contract_without_dates() -> None:
    name = "Test Contract"
    publishers = make_publishers()

    contract_create(name, publishers)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(actual, name, publishers, is_active=True, start_date=None, end_date=None)


@pytest.mark.django_db
def test__contract_create__today_outside_date_range__contract_is_inactive() -> None:
    name = "Test Contract"
    publishers = make_publishers()

    contract_create(name, publishers, START_DATE, END_DATE, now=AFTER_END_DATE)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(actual, name, publishers, is_active=False)


@pytest.mark.django_db
def test__contract_create__only_start_date_before_now__contract_is_active() -> None:
    name = "Test Contract"
    publishers = make_publishers()

    contract_create(name, publishers, start_date=START_DATE, now=INSIDE_DATE_RANGE)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(
        actual, name, publishers, start_date=START_DATE, end_date=None, is_active=True
    )


@pytest.mark.django_db
def test__contract_create__only_start_date_after_now__contract_is_not_active() -> None:
    name = "Test Contract"
    publishers = make_publishers()

    contract_create(name, publishers, start_date=START_DATE, now=BEFORE_START_DATE)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(
        actual, name, publishers, start_date=START_DATE, end_date=None, is_active=False
    )


@pytest.mark.django_db
def test__contract_create__only_end_date_after_now__contract_is_active() -> None:
    name = "Test Contract"
    publishers = make_publishers()

    contract_create(name, publishers, end_date=END_DATE, now=INSIDE_DATE_RANGE)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(
        actual, name, publishers, start_date=None, end_date=END_DATE, is_active=True
    )


@pytest.mark.django_db
def test__contract_create__only_end_date_before_now__contract_is_not_active() -> None:
    name = "Test Contract"
    publishers = make_publishers()

    contract_create(name, publishers, end_date=END_DATE, now=AFTER_END_DATE)

    actual = Contract.objects.get(name=name)
    assert_contract_equals(
        actual, name, publishers, start_date=None, end_date=END_DATE, is_active=False
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_contract_view__can_create_contract(client: Client) -> None:
    name = "Test Contract"
    publishers = make_publishers()

    client.post(
        "/contracts/create/",
        data={
            "name": name,
            "publishers": [publisher.pk for publisher in publishers],
            "start_date": START_DATE,
            "end_date": END_DATE,
        },
    )

    actual = Contract.objects.get(name=name)
    assert_contract_equals(actual, name, publishers, is_active=True)


def assert_contract_equals(
    contract: Contract,
    name: str,
    publishers: list[Publisher],
    start_date: datetime.date | None = START_DATE,
    end_date: datetime.date | None = END_DATE,
    *,
    is_active: bool,
) -> None:
    assert contract.name == name
    assert list(contract.publishers.all()) == publishers
    assert contract.start_date == start_date
    assert contract.end_date == end_date
    assert contract.is_active == is_active


def make_publishers() -> list[Publisher]:
    return Publisher.objects.bulk_create(
        [Publisher(name="Publisher 1"), Publisher(name="Publisher 2")]
    )

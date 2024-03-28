import datetime

import pytest
from django.test import Client

from coda.apps.contracts.models import Contract, ContractExpiredError
from coda.apps.contracts.services import DateRange, contract_create
from coda.apps.publishers.models import Publisher

START_DATE = datetime.date(2024, 1, 1)
END_DATE = datetime.date(2024, 12, 31)

INSIDE_DATE_RANGE = datetime.date(2024, 6, 1)
AFTER_END_DATE = datetime.date(2025, 6, 1)
BEFORE_START_DATE = datetime.date(2023, 6, 1)

CONTRACT_NAME = "Test Contract"


def date_range() -> DateRange:
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
    contract_create(CONTRACT_NAME, publishers, date_range())

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, date_range())
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

    contract_create(CONTRACT_NAME, publishers, date_range())

    actual = Contract.objects.get(name=CONTRACT_NAME)
    assert_contract_equals(actual, publishers, date_range())
    assert actual.is_active(AFTER_END_DATE) is False


@pytest.mark.django_db
def test__created_contract_in_date_range__now_outside_date_range__contract_is_inactive() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers, date_range())

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
def test__created_active_contract__deactivate__contract_is_inactive() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers, date_range())

    sut.make_inactive()

    assert sut.is_active() is False


@pytest.mark.django_db
def test__contract_made_inactive__make_active__contract_is_active() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers)
    sut.make_inactive()

    sut.make_active()

    assert sut.is_active() is True


@pytest.mark.django_db
def test__contract_has_ended__make_active__raises_contract_expired_exception() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers, date_range())

    now = AFTER_END_DATE
    with pytest.raises(ContractExpiredError):
        sut.make_active(now)

    assert sut.is_active(now) is False


@pytest.mark.django_db
def test__contract_inactive__make_active_until_now__contract_is_active_with_new_end_date() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers, date_range())

    now = END_DATE + datetime.timedelta(days=1)
    sut.make_active(now, until=now)

    assert sut.is_active(now) is True
    assert sut.end_date == now


@pytest.mark.django_db
def test__contract_inactive__make_active_until_past_date__raises_value_error() -> None:
    publishers = make_publishers()
    sut = contract_create(CONTRACT_NAME, publishers, date_range())

    now = END_DATE + datetime.timedelta(days=2)
    until = END_DATE + datetime.timedelta(days=1)
    with pytest.raises(ValueError):
        sut.make_active(now, until=until)

    assert sut.is_active(now) is False


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
    assert_contract_equals(actual, publishers, date_range())
    assert actual.is_active(INSIDE_DATE_RANGE) is True


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__inactive_contract__status_view__make_active__contract_is_active(client: Client) -> None:
    publishers = make_publishers()
    contract = contract_create(CONTRACT_NAME, publishers)
    contract.make_inactive()

    client.post(f"/contracts/{contract.pk}/status/", data={"status": "active"})

    contract.refresh_from_db()
    assert contract.is_active() is True


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__active_contract__status_view__make_inactive__contract_is_inactive(client: Client) -> None:
    publishers = make_publishers()
    contract = contract_create(CONTRACT_NAME, publishers)

    client.post(f"/contracts/{contract.pk}/status/", data={"status": "inactive"})

    contract.refresh_from_db()
    assert contract.is_active() is False


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_has_ended__status_view_make_active_with_new_end_date__contract_is_active_with_new_end_date(
    client: Client,
) -> None:
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date_range = DateRange(end_date=yesterday)

    publishers = make_publishers()
    contract = contract_create(CONTRACT_NAME, publishers, date_range)

    client.post(
        f"/contracts/{contract.pk}/status/",
        data={"status": "active", "until": today},
    )

    contract.refresh_from_db()
    assert contract.is_active() is True
    assert contract.end_date == today


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

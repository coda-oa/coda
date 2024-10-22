import datetime

import pytest
from django.test import Client

from coda.apps.contracts.services import contract_create, get_by_id
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.contract import Contract, ContractId, PublisherId
from coda.date import DateRange
from coda.publication import JournalId
from coda.string import NonEmptyStr
from tests import modelfactory

START_DATE = datetime.date(2024, 1, 1)
END_DATE = datetime.date(2024, 12, 31)
INSIDE_DATE_RANGE = datetime.date(2024, 6, 1)

CONTRACT_NAME = NonEmptyStr("Test Contract")


def date_range() -> DateRange:
    return DateRange.create(start=START_DATE, end=END_DATE)


@pytest.mark.django_db
def test__can_create_contract__new() -> None:
    publishers_ids = make_publishers()
    journal_ids = make_journals(publishers_ids)

    expected = Contract.new(CONTRACT_NAME, publishers_ids, date_range(), journal_ids)

    contract_id = contract_create(expected)

    actual = get_by_id(contract_id)
    assert_contract_eq(actual, expected)


def make_publishers() -> list[PublisherId]:
    return [PublisherId(modelfactory.publisher().pk) for _ in range(2)]


def make_journals(publishers_ids: list[PublisherId]) -> list[JournalId]:
    return [JournalId(modelfactory.journal(publisher_id).pk) for publisher_id in publishers_ids]


def assert_contract_eq(actual: Contract, expected: Contract) -> None:
    assert actual.name == expected.name
    assert actual.publishers == expected.publishers
    assert actual.period == expected.period
    assert actual.journals == expected.journals


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_contract_view__can_create_contract(client: Client) -> None:
    publishers = make_publishers()
    publisher_form_data = to_htmx_formset_data(
        [{"entity_id": pid} for pid in publishers], prefix="publishers"
    )
    journals = make_journals(publishers)
    journal_form_data = to_htmx_formset_data(
        [{"entity_id": jid} for jid in journals], prefix="journals"
    )

    expected = Contract.new(CONTRACT_NAME, publishers, date_range(), journals)

    client.post(
        "/contracts/create/",
        {
            "name": CONTRACT_NAME,
            "start_date": START_DATE,
            "end_date": END_DATE,
        }
        | publisher_form_data
        | journal_form_data,
    )

    actual = get_by_id(ContractId(1))
    assert_contract_eq(actual, expected)


# @pytest.mark.django_db
# @pytest.mark.usefixtures("logged_in")
# def test__inactive_contract__status_view__make_active__contract_is_active(client: Client) -> None:
#     publishers = make_publishers()
#     contract = contract_create(CONTRACT_NAME, publishers)
#     contract.make_inactive()

#     client.post(f"/contracts/{contract.pk}/status/", data={"status": "active"})

#     contract.refresh_from_db()
#     assert contract.is_active() is True


# @pytest.mark.django_db
# @pytest.mark.usefixtures("logged_in")
# def test__active_contract__status_view__make_inactive__contract_is_inactive(client: Client) -> None:
#     publishers = make_publishers()
#     contract = contract_create(CONTRACT_NAME, publishers)

#     client.post(f"/contracts/{contract.pk}/status/", data={"status": "inactive"})

#     contract.refresh_from_db()
#     assert contract.is_active() is False


# @pytest.mark.django_db
# @pytest.mark.usefixtures("logged_in")
# def test__contract_has_ended__status_view_make_active_with_new_end_date__contract_is_active_with_new_end_date(
#     client: Client,
# ) -> None:
#     today = datetime.date.today()
#     yesterday = today - datetime.timedelta(days=1)
#     date_range = DateRange.create(end=yesterday)

#     publishers = make_publishers()
#     contract = contract_create(CONTRACT_NAME, publishers, date_range)

#     client.post(
#         f"/contracts/{contract.pk}/status/",
#         data={"status": "active", "until": today},
#     )

#     contract.refresh_from_db()
#     assert contract.is_active() is True
#     assert contract.end_date == today


# def assert_contract_equals(
#     contract: ContractModel, publishers: list[Publisher], date_range: DateRange | None = None
# ) -> None:
#     date_range = date_range or no_dates()
#     assert contract.name == CONTRACT_NAME
#     assert list(contract.publishers.all()) == publishers
#     assert contract.start_date == date_range.start
#     assert contract.end_date == date_range.end


# def make_publishers() -> list[Publisher]:
#     return Publisher.objects.bulk_create(
#         [Publisher(name="Publisher 1"), Publisher(name="Publisher 2")]
#     )

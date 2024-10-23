import datetime

import pytest
from django.test import Client

from coda.apps.contracts.services import contract_create, first, get_by_id
from coda.apps.htmx_components.converters import to_htmx_formset_data
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

    contract_id = contract_create(expected)

    actual = get_by_id(contract_id)
    assert_contract_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_contract_view__can_create_contract(client: Client) -> None:
    base_contract_data = {
        "name": CONTRACT_NAME,
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
    }

    publishers = make_publishers()
    publisher_form_data = to_htmx_formset_data(entity_form_data(publishers), prefix="publishers")

    journals = make_journals(publishers)
    journal_form_data = to_htmx_formset_data(entity_form_data(journals), prefix="journals")

    data = base_contract_data | publisher_form_data | journal_form_data

    client.post("/contracts/create/", data)

    actual = first()
    expected = make_contract(publishers, journals)
    assert actual is not None
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


def entity_form_data(entities: list[PublisherId] | list[JournalId]) -> list[dict[str, str]]:
    return [{"entity_id": str(id)} for id in entities]


def date_range() -> DateRange:
    return DateRange.create(start=START_DATE, end=END_DATE)

from collections.abc import Iterable
import datetime

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.contracts import services
from coda.apps.contracts.forms import ContractForm, EntityFormset
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.contract import Contract, PublisherId
from coda.date import DateRange
from coda.publication import JournalId
from coda.string import NonEmptyStr
from tests.contracts.test_contract_services import (
    assert_contract_eq,
    make_contract,
    make_journals,
    make_publishers,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_contract_view__can_create_contract(client: Client) -> None:
    publishers = make_publishers()
    journals = make_journals(publishers)
    expected = make_contract(publishers, journals)

    publisher_form_data = to_htmx_formset_data(entity_form_data(publishers), prefix="publishers")
    journal_form_data = to_htmx_formset_data(entity_form_data(journals), prefix="journals")
    data = contract_form_data(expected) | publisher_form_data | journal_form_data

    client.post(reverse("contracts:create"), data)

    actual = services.first()
    assert actual is not None
    assert_contract_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_saved_contract__update_contract_view__updates_contract(client: Client) -> None:
    contract = make_contract(make_publishers(), make_journals(make_publishers()))
    contract_id = services.save(contract)

    expected = Contract(
        id=contract_id,
        name=NonEmptyStr("Updated"),
        publishers=tuple(make_publishers()),
        journals=tuple(make_journals(make_publishers())),
        period=DateRange(start=datetime.date(2025, 1, 1), end=datetime.date(2025, 12, 31)),
    )

    data = (
        contract_form_data(expected)
        | to_htmx_formset_data(entity_form_data(expected.publishers), prefix="publishers")
        | to_htmx_formset_data(entity_form_data(expected.journals), prefix="journals")
    )

    client.post(reverse("contracts:update", kwargs={"pk": contract_id}), data)

    actual = services.get_by_id(contract_id)
    assert_contract_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_saved_contract__goto_update_contract_view__shows_contract(client: Client) -> None:
    contract = make_contract(make_publishers(), make_journals(make_publishers()))
    contract_id = services.save(contract)

    response = client.get(reverse("contracts:update", kwargs={"pk": contract_id}))

    contract_form: ContractForm = response.context["contract_form"]
    contract_form.full_clean()
    assert contract_form.get_name() == contract.name
    assert contract_form.get_period() == contract.period

    publisher_formset: EntityFormset = response.context["publisher_formset"]
    publisher_formset.full_clean()
    assert publisher_formset.entity_ids() == list(contract.publishers)

    journal_formset: EntityFormset = response.context["journal_formset"]
    journal_formset.full_clean()
    assert journal_formset.entity_ids() == list(contract.journals)


def contract_form_data(contract: Contract) -> dict[str, str]:
    return {
        "name": contract.name,
        "start_date": contract.period.start.isoformat(),
        "end_date": contract.period.end.isoformat(),
    }


def entity_form_data(entities: Iterable[PublisherId] | Iterable[JournalId]) -> list[dict[str, str]]:
    return [{"entity_id": str(id)} for id in entities]

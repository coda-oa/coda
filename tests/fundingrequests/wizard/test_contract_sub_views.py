import datetime
from typing import Any

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse

from coda.apps.contracts import repository
from coda.apps.fundingrequests.forms import ContractForm, ContractFormset
from coda.apps.fundingrequests.views.wizard.steps.contract_step import ContractStep
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import ContractYearDto
from coda.apps.wizard import Store
from coda.domain.contract import Contract
from coda.domain.date import DateRange
from coda.domain.string import NonEmptyStr
from tests import domainfactory
from tests.test_wizard import DictStore

contract_formset_url = reverse(ContractFormset.name)


_request_factory = RequestFactory()


@pytest.mark.django_db
def test__contract_step__get_context_data__formset_choices_contain_contracts() -> None:
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)

    sut = ContractStep()

    request = _request_factory.post("/", {"contracts-total_forms": "1"})
    context = sut.get_context_data(request, DictStore())

    formset: ContractFormset = context["contract_formset"]
    form = formset.forms[0]
    assert contract_choices(form) == [(c.id, c.name) for c in contracts]


@pytest.mark.django_db
def test__contract_step__post_contracts__formset_contains_contracts() -> None:
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)

    sut = ContractStep()

    post_data = contract_formset_post_data(contracts)
    request = _request_factory.post(contract_formset_url, post_data)
    context = sut.get_context_data(request, DictStore())

    formset: ContractFormset = context["contract_formset"]
    assert_contracts_selected_in_formset(contracts, formset)


@pytest.mark.django_db
def test__contract_step__contracts_in_store__formset_contains_contracts() -> None:
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)
    store = store_with_contracts(contracts)

    sut = ContractStep()

    request = _request_factory.get(contract_formset_url)
    context = sut.get_context_data(request, store)

    formset: ContractFormset = context["contract_formset"]
    assert_contracts_selected_in_formset(contracts, formset)


@pytest.mark.django_db
def test__contract_step__inactive_contracts_in_store__formset_includes_inactive_contracts() -> None:
    contracts = [domainfactory.contract(period=DateRange.create(end=datetime.date.min))]
    save_all(contracts)
    store = store_with_contracts(contracts)

    sut = ContractStep()

    request = _request_factory.post(contract_formset_url)
    context = sut.get_context_data(request, store)

    formset: ContractFormset = context["contract_formset"]
    assert_contracts_selected_in_formset(contracts, formset)


@pytest.mark.django_db
def test__contract_step__contracts_in_store_and_post_data__prefers_post_data() -> None:
    post_contracts = [domainfactory.contract() for _ in range(2)]
    store_contracts = [domainfactory.contract() for _ in range(3)]
    save_all(post_contracts + store_contracts)

    store = store_with_contracts(store_contracts)
    post_data = contract_formset_post_data(post_contracts)
    sut = ContractStep()

    request = _request_factory.post(contract_formset_url, post_data)
    context = sut.get_context_data(request, store)

    formset: ContractFormset = context["contract_formset"]
    assert_contracts_selected_in_formset(post_contracts, formset)


@pytest.mark.django_db
def test__contract_step__done__stores_contracts_in_store() -> None:
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)

    sut = ContractStep()
    store = DictStore()

    post_data = contract_formset_post_data(contracts)
    request = _request_factory.post("", post_data)

    sut.done(request, store)

    assert store["contracts"] == [
        ContractYearDto.from_contract_year(c.in_first_year()).to_post_data() for c in contracts
    ]


@pytest.mark.django_db
def test__contract_step__same_contract_in_different_years__done__both_contract_years_in_store() -> (
    None
):
    store = DictStore()
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)
    sut = ContractStep()

    first_contract = contracts[0]
    first_contract_year = first_contract.in_first_year()
    second_contract_year = first_contract.in_year(first_contract_year.year + 1)
    contract_years = to_htmx_formset_data(
        [
            {"contract": first_contract_year.contract_id, "year": first_contract_year.year},
            {"contract": second_contract_year.contract_id, "year": second_contract_year.year},
        ],
        prefix="contracts",
    )
    request = _request_factory.post("", contract_years)

    sut.done(request, store)

    assert len(store["contracts"]) == 2
    assert {c["year"] for c in store["contracts"]} == {
        first_contract_year.year,
        second_contract_year.year,
    }


def contract_formset_post_data(contracts: list[Contract]) -> dict[str, Any]:
    return to_htmx_formset_data(
        [{"contract": str(c.id), "year": c.in_first_year().year} for c in contracts],
        prefix="contracts",
    )


def store_with_contracts(contracts: list[Contract]) -> Store:
    store = DictStore()
    store["contracts"] = [
        ContractYearDto.from_contract_year(c.in_first_year()).to_post_data() for c in contracts
    ]
    store.save()
    return store


def selected_contract_ids(formset: ContractFormset) -> list[int]:
    return [int(form.cleaned_data["contract"]) for form in formset.forms]


def contract_choices(form: ContractForm) -> list[tuple[int, str]]:
    return list(form.fields["contract"].widget.choices)


def save_all(contracts: list[Contract]) -> None:
    for contract in contracts:
        contract.id = repository.create(contract)


def assert_contracts_selected_in_formset(
    contracts: list[Contract], formset: ContractFormset
) -> None:
    assert selected_contract_ids(formset) == [c.id for c in contracts]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__inactive_contracts_enabled__view_returns_formset_with_inactive_contracts(
    client: Client,
) -> None:
    contract = Contract.new(
        NonEmptyStr("Inactive Contract"),
        period=DateRange.create(end=datetime.date.min),
    )
    contract.id = repository.create(contract)

    response = client.post(
        reverse("fundingrequests:include_inactive_contracts"),
        {
            "include_inactive": "true",
            "contracts-total_forms": "1",
            "contracts-form-1-contract": "",
            "contracts-form-1-year": "",
        },
    )

    assert f'option value="{contract.id}"' in response.content.decode()

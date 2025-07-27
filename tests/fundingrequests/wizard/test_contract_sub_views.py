import datetime
from typing import Any
from django.http import HttpRequest
from django.test import Client, RequestFactory
from django.urls import reverse
import pytest

from coda.apps.contracts import repository
from coda.apps.fundingrequests.forms import ContractForm, ContractFormset
from coda.domain.contract import Contract
from coda.domain.date import DateRange
from coda.domain.string import NonEmptyStr
from tests import domainfactory

contract_formset_url = reverse(ContractFormset.name)


class ContractStep:
    def get_context_data(self, request: HttpRequest) -> dict[str, Any]:
        return {"formset": ContractFormset(request.POST, prefix="contracts")}


_request_factory = RequestFactory()


@pytest.mark.django_db
def test__contract_step__get_context_data__formset_choices_contain_contracts() -> None:
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)

    sut = ContractStep()

    request = _request_factory.post("/", {"contracts-total_forms": "1"})
    context = sut.get_context_data(request)

    formset: ContractFormset = context["formset"]
    form = formset.forms[0]
    assert contract_choices(form) == [(c.id, c.name) for c in contracts]


@pytest.mark.django_db
def test__contract_step__post_contracts__formset_contains_contracts() -> None:
    contracts = [domainfactory.contract() for _ in range(3)]
    save_all(contracts)

    sut = ContractStep()

    request = _request_factory.post(
        contract_formset_url,
        {
            "contracts-total_forms": "3",
            "contracts-form-1-contract": contracts[0].id,
            "contracts-form-1-year": contracts[0].in_first_year().year,
            "contracts-form-2-contract": contracts[1].id,
            "contracts-form-2-year": contracts[1].in_first_year().year,
            "contracts-form-3-contract": contracts[2].id,
            "contracts-form-3-year": contracts[2].in_first_year().year,
        },
    )
    context = sut.get_context_data(request)

    formset: ContractFormset = context["formset"]
    actual = [int(form.cleaned_data["contract"]) for form in formset.forms]
    expected = [c.id for c in contracts]
    assert actual == expected


def contract_choices(form: ContractForm) -> list[tuple[int, str]]:
    return list(form.fields["contract"].widget.choices)


def save_all(contracts: list[Contract]) -> None:
    for contract in contracts:
        contract.id = repository.create(contract)


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

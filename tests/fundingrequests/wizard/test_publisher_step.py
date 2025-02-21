import datetime

import pytest
from django.test import RequestFactory

from coda.apps.contracts.repository import save
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import (
    PublisherStep,
    PublisherStepDto,
)
from coda.apps.publications.dto import ContractYearDto
from coda.contract import ContractId
from coda.date import DateRange
from tests import domainfactory, modelfactory
from tests.test_wizard import DictStore


@pytest.mark.django_db
def test__publisher_step__with_publisher_and_contracts__is_valid() -> None:
    publisher = modelfactory.publisher()
    contract = domainfactory.contract()
    contract_id = save(contract)
    contract.id = contract_id
    contract_year = domainfactory.contract_year(contract)

    sut = PublisherStep()
    request = RequestFactory().post(
        "/",
        PublisherStepDto(
            publisher=publisher.pk,
            contracts=[ContractYearDto.from_contract_year(contract_year)],
        ).page_input(),
    )

    assert sut.is_valid(request, DictStore())


@pytest.mark.django_db
def test__publisher_step__without_publisher__is_invalid() -> None:
    sut = PublisherStep()
    request = RequestFactory().post("/", {})

    assert not sut.is_valid(request, DictStore())


@pytest.mark.django_db
def test__publisher_step__with_contract_year_outside_period__is_invalid() -> None:
    publisher = modelfactory.publisher()
    contract = domainfactory.contract(period=DateRange.create(start=datetime.date(2024, 1, 1)))
    contract_id = save(contract)

    invalid_year = 1800

    sut = PublisherStep()

    request = RequestFactory().post(
        "/",
        PublisherStepDto(
            publisher=publisher.pk,
            contracts=[ContractYearDto(contract=contract_id, year=invalid_year)],
        ).page_input(),
    )

    assert not sut.is_valid(request, DictStore())


@pytest.mark.django_db
def test__publisher_step__with_publisher_and_contracts__done_saves_data_to_store() -> None:
    publisher = modelfactory.publisher()
    contract = domainfactory.contract()
    contract_id = save(contract)
    contract.id = contract_id
    contract_year = domainfactory.contract_year(contract)

    sut = PublisherStep()
    expected = PublisherStepDto(
        publisher=publisher.pk,
        contracts=[ContractYearDto(contract=contract_id, year=contract_year.year)],
    )

    request = RequestFactory().post("/", expected.page_input())
    store = DictStore()

    sut.done(request, store)

    publisher_step = store["publisher_step"]
    assert publisher_step == expected.to_post_data()


@pytest.mark.django_db
def test__publisher_step_data_in_store__when_posting_invalid_data__returns_context_with_posted_data() -> (
    None
):
    publisher = modelfactory.publisher()
    contract = domainfactory.contract()
    contract_id = save(contract)
    contract.id = contract_id

    store = DictStore()
    stored_data = PublisherStepDto(
        publisher=0,
        contracts=[ContractYearDto(contract=ContractId(0), year=2024)],
    )
    store["publisher_step"] = stored_data.to_post_data()
    store.save()

    sut = PublisherStep()

    invalid_year = 1800
    expected = PublisherStepDto(
        publisher=publisher.pk,
        contracts=[ContractYearDto(contract=contract_id, year=invalid_year)],
    )

    request = RequestFactory().post("/", expected.page_input())

    context = sut.get_context_data(request, store)

    assert context["selected_publisher"] == publisher
    assert context["publishers"] == [publisher]
    assert [d["contract"].id for d in context["contract_formset"].data] == [contract.id]

import pytest
from django.test import RequestFactory

from coda.apps.contracts.services import contract_create
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import (
    PublisherStep,
    PublisherStepDto,
)
from tests import domainfactory, modelfactory
from tests.test_wizard import DictStore


@pytest.mark.django_db
def test__publisher_step__with_publisher_and_contracts__is_valid() -> None:
    publisher = modelfactory.publisher()
    contract_id = contract_create(domainfactory.contract())

    sut = PublisherStep()
    request = RequestFactory().post(
        "/",
        PublisherStepDto(
            publisher=publisher.pk,
            contracts=[contract_id],
        ).page_input(),
    )

    assert sut.is_valid(request, DictStore())


@pytest.mark.django_db
def test__publisher_step__without_publisher__is_invalid() -> None:
    sut = PublisherStep()
    request = RequestFactory().post("/", {})

    assert not sut.is_valid(request, DictStore())


@pytest.mark.django_db
def test__publisher_step__with_publisher_and_contracts__done_saves_data_to_store() -> None:
    publisher = modelfactory.publisher()
    contract_id = contract_create(domainfactory.contract())

    sut = PublisherStep()
    expected = PublisherStepDto(publisher=publisher.pk, contracts=[contract_id])

    request = RequestFactory().post("/", expected.page_input())
    store = DictStore()

    sut.done(request, store)

    publisher_step = store["publisher_step"]
    assert publisher_step == expected.to_post_data()

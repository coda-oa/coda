import pytest
from django.test.client import RequestFactory

from coda.apps.fundingrequests.views.wizard.wizardsteps import FundingStep
from tests import modelfactory
from tests.test_wizard import DictStore

_request_factory = RequestFactory()

cost_data = {
    "estimated_cost": 1000,
    "estimated_cost_currency": "EUR",
    "payment_method": "direct",
}


@pytest.mark.django_db
def test__funding_step__valid_data__is_valid() -> None:
    funding_org = modelfactory.funding_organization()
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post(
        "/",
        cost_data
        | {
            "form-1-organization": funding_org.pk,
            "form-1-project_id": "123",
            "form-1-project_name": "Test Project",
        },
    )

    assert funding_step.is_valid(request, store) is True


@pytest.mark.django_db
def test__funding_step__without_external_funding__is_valid() -> None:
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post("/", cost_data)

    assert funding_step.is_valid(request, store) is True


@pytest.mark.django_db
def test__funding_step__empty_external_funding__is_valid() -> None:
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post(
        "/",
        cost_data
        | {
            "organization": "",
            "project_id": "",
            "project_name": "",
        },
    )

    assert funding_step.is_valid(request, store) is True


@pytest.mark.django_db
def test__funding_step__only_organization_without_project_id__is_invalid() -> None:
    funding_org = modelfactory.funding_organization()
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post(
        "/",
        cost_data
        | {
            "form-1-organization": funding_org.pk,
            "form-1-project_id": "",
            "form-1-project_name": "Test Project",
        },
    )

    assert funding_step.is_valid(request, store) is False


@pytest.mark.django_db
def test__funding_step__only_project_id_without_organization__is_invalid() -> None:
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post(
        "/",
        cost_data
        | {
            "form-1-organization": "",
            "form-1-project_id": "123",
            "form-1-project_name": "Test Project",
        },
    )

    assert funding_step.is_valid(request, store) is False


@pytest.mark.django_db
def test__funding_step__without_external_funding__done_does_not_store_funding() -> None:
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post("/", cost_data)
    funding_step.done(request, store)

    assert store.get("funding") is None


@pytest.mark.django_db
def test__funding_step__with_previous_funding__subnmitting_without_external_funding__overrides_old_funding_in_store() -> (
    None
):
    store = DictStore()
    funding_org = modelfactory.funding_organization()
    store["funding"] = {
        "organization": funding_org.pk,
        "project_id": "123",
        "project_name": "Test Project",
    }

    funding_step = FundingStep()

    request = _request_factory.post("/", cost_data)
    funding_step.done(request, store)

    assert store.get("funding") is None

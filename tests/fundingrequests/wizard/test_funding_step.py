import pytest
from django.test.client import RequestFactory

from coda.apps.fundingrequests.forms import ExternalFundingFormset
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
            "total_forms": 1,
            "form-1-organization": funding_org.pk,
            "form-1-project_id": "123",
            "form-1-project_name": "Test Project",
        },
    )

    assert funding_step.is_valid(request, store) is True


@pytest.mark.django_db
def test__valid_funding_step__done__saves_data_in_store() -> None:
    funding_org = modelfactory.funding_organization()
    store = DictStore()
    funding_step = FundingStep()

    request = _request_factory.post(
        "/",
        cost_data
        | {
            "total_forms": 2,
            "form-1-organization": funding_org.pk,
            "form-1-project_id": "123",
            "form-1-project_name": "Test Project",
            "form-2-organization": funding_org.pk,
            "form-2-project_id": "456",
            "form-2-project_name": "Another Project",
        },
    )

    funding_step.done(request, store)

    assert store.get("funding") == [
        {
            "organization": funding_org.pk,
            "project_id": "123",
            "project_name": "Test Project",
        },
        {
            "organization": funding_org.pk,
            "project_id": "456",
            "project_name": "Another Project",
        },
    ]


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
            "total_forms": 1,
            "form-1-organization": "",
            "form-1-project_id": "",
            "form-1-project_name": "",
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
            "total_forms": 1,
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
            "total_forms": 1,
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
    store["funding"] = [
        {
            "organization": funding_org.pk,
            "project_id": "123",
            "project_name": "Test Project",
        }
    ]

    funding_step = FundingStep()

    request = _request_factory.post("/", cost_data)
    funding_step.done(request, store)

    assert store.get("funding") is None


@pytest.mark.django_db
def test__funding_step__with_previous_funding__has_funding_in_response_context() -> None:
    store = DictStore()
    funding_org = modelfactory.funding_organization()
    store["funding"] = [
        {
            "organization": funding_org.pk,
            "project_id": "123",
            "project_name": "Test Project",
        }
    ]
    store.save()

    funding_step = FundingStep()

    request = _request_factory.get("/")
    ctx = funding_step.get_context_data(request, store)

    formset: ExternalFundingFormset = ctx["funding_formset"]
    assert formset.is_valid()
    assert formset.to_dto() == store["funding"]


@pytest.mark.django_db
def test__funding_step__with_previous_funding__on_post__uses_funding_from_request() -> None:
    store = DictStore()
    funding_org = modelfactory.funding_organization()
    store["funding"] = [
        {
            "organization": funding_org.pk,
            "project_id": "123",
            "project_name": "Test Project",
        }
    ]
    expected = {
        "organization": funding_org.pk,
        "project_id": "5432",
        "project_name": "New Project",
    }

    funding_step = FundingStep()

    request = _request_factory.post(
        "/",
        cost_data
        | {
            "total_forms": 1,
            "form-1-organization": expected["organization"],
            "form-1-project_id": expected["project_id"],
            "form-1-project_name": expected["project_name"],
        },
    )

    ctx = funding_step.get_context_data(request, store)

    formset: ExternalFundingFormset = ctx["funding_formset"]
    assert formset.is_valid()
    assert formset.to_dto() == [expected]

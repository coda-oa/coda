import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import (
    ExternalFunding,
    FundingRequest as FundingRequestModel,
)
from coda.apps.fundingrequests.models import FundingRequestContact, FundingRequestReview
from coda.apps.invoices.models import Position
from coda.apps.opencost.models import OpenCostReport, OpenCostReportPublication
from coda.apps.publications.models import Publication
from coda.apps.users.models import User
from coda.contexts.fundingrequest.services import fundingrequests as fr_services
from coda.domain.fundingrequest import FundingRequestId
from tests import modelfactory


@pytest.fixture
def logged_in_client(client: Client) -> Client:
    client.force_login(User.objects.create_user(username="fr-delete-user"))
    return client


def add_invoice_position(publication: Publication) -> Position:
    return Position.objects.create(
        invoice=modelfactory.invoice(),
        description="Publication fee",
        cost_amount=100,
        cost_currency="EUR",
        publication=publication,
    )


def add_opencost_report_entry(publication: Publication) -> None:
    report = OpenCostReport.objects.create(
        title="Report",
        period_start="2024-01-01",
        period_end="2024-12-31",
    )
    OpenCostReportPublication.objects.create(
        report=report,
        publication=publication,
        title=publication.title,
    )


@pytest.mark.django_db
def test__delete_fundingrequest__without_references__deletes_request_and_owned_data() -> None:
    fr = modelfactory.fundingrequest()
    publication_id = fr.publication_id
    review_id = fr.review_id
    contact_id = fr.extra_contact_id

    fr_services.delete_fundingrequest(FundingRequestId(fr.pk))

    assert not FundingRequestModel.objects.filter(pk=fr.pk).exists()
    assert not Publication.objects.filter(pk=publication_id).exists()
    assert not FundingRequestReview.objects.filter(pk=review_id).exists()
    assert not FundingRequestContact.objects.filter(pk=contact_id).exists()
    assert not ExternalFunding.objects.filter(funding_request_id=fr.pk).exists()


@pytest.mark.django_db
def test__can_delete_fundingrequest__with_invoice_position__is_blocked() -> None:
    fr = modelfactory.fundingrequest()
    add_invoice_position(fr.publication)

    can_delete, blocking = fr_services.can_delete_fundingrequest(FundingRequestId(fr.pk))

    assert not can_delete
    assert any(ref.description.startswith("Invoice ") for ref in blocking)
    assert all(ref.url for ref in blocking)


@pytest.mark.django_db
def test__can_delete_fundingrequest__with_opencost_report_entry__is_blocked() -> None:
    fr = modelfactory.fundingrequest()
    add_opencost_report_entry(fr.publication)

    can_delete, blocking = fr_services.can_delete_fundingrequest(FundingRequestId(fr.pk))

    assert not can_delete
    assert any(ref.description.startswith("OpenCost report ") for ref in blocking)
    assert all(ref.url for ref in blocking)


@pytest.mark.django_db
def test__can_delete_fundingrequest__multiple_positions_on_one_invoice__lists_invoice_once() -> (
    None
):
    fr = modelfactory.fundingrequest()
    invoice = modelfactory.invoice()
    for description in (" APC", " VAT"):
        Position.objects.create(
            invoice=invoice,
            description=description,
            cost_amount=100,
            cost_currency="EUR",
            publication=fr.publication,
        )

    can_delete, blocking = fr_services.can_delete_fundingrequest(FundingRequestId(fr.pk))

    assert not can_delete
    assert len([ref for ref in blocking if ref.description.startswith("Invoice ")]) == 1


@pytest.mark.django_db
def test__delete_fundingrequest__referenced__raises_and_keeps_request() -> None:
    fr = modelfactory.fundingrequest()
    add_invoice_position(fr.publication)

    with pytest.raises(ValueError, match="Cannot delete funding request"):
        fr_services.delete_fundingrequest(FundingRequestId(fr.pk))

    assert FundingRequestModel.objects.filter(pk=fr.pk).exists()


@pytest.mark.django_db
def test__request_delete_view__without_references__shows_enabled_delete(
    logged_in_client: Client,
) -> None:
    fr = modelfactory.fundingrequest()

    response = logged_in_client.get(
        reverse("fundingrequests:fundingrequest_request_delete", kwargs={"pk": fr.pk})
    )

    content = response.content.decode()
    assert str(fr.request_id) in content
    assert "This action cannot be undone" in content
    assert 'hx-post="' in content


@pytest.mark.django_db
def test__request_delete_view__referenced__links_the_invoice(
    logged_in_client: Client,
) -> None:
    fr = modelfactory.fundingrequest()
    position = add_invoice_position(fr.publication)
    invoice_url = reverse("invoices:detail", kwargs={"pk": position.invoice.pk})

    response = logged_in_client.get(
        reverse("fundingrequests:fundingrequest_request_delete", kwargs={"pk": fr.pk})
    )

    content = response.content.decode()
    assert "it is referenced by:" in content
    assert f'<a href="{invoice_url}">' in content
    assert "disabled>Delete</button>" in content


@pytest.mark.django_db
def test__delete_view__without_references__deletes_and_redirects_to_list(
    logged_in_client: Client,
) -> None:
    fr = modelfactory.fundingrequest()

    response = logged_in_client.post(
        reverse("fundingrequests:fundingrequest_delete", kwargs={"pk": fr.pk})
    )

    assert response["HX-Redirect"] == reverse("fundingrequests:list")
    assert not FundingRequestModel.objects.filter(pk=fr.pk).exists()


@pytest.mark.django_db
def test__delete_view__referenced__redirects_back_with_error(
    logged_in_client: Client,
) -> None:
    fr = modelfactory.fundingrequest()
    add_invoice_position(fr.publication)

    response = logged_in_client.post(
        reverse("fundingrequests:fundingrequest_delete", kwargs={"pk": fr.pk})
    )

    assert response["HX-Redirect"] == reverse("fundingrequests:detail", kwargs={"pk": fr.pk})
    assert FundingRequestModel.objects.filter(pk=fr.pk).exists()

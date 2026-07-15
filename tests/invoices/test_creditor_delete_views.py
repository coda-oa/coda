import datetime

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from coda.apps.invoices import repository
from coda.apps.invoices.models import Creditor
from coda.domain.finance.invoice import CreditorId, Invoice


@pytest.fixture
def creditor() -> Creditor:
    return Creditor.objects.create(name="Test Creditor")


@pytest.fixture
def archived_creditor() -> Creditor:
    c = Creditor.objects.create(name="Archived Creditor", archived_at=timezone.now())
    c.save()
    return c


def assert_content_contains(content: str, *items: str) -> None:
    for item in items:
        assert item in content


def assert_content_excludes(content: str, *items: str) -> None:
    for item in items:
        assert item not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__creditor_detail_view__shows_creditor_name(client: Client, creditor: Creditor) -> None:
    response = client.get(reverse("invoices:creditor_detail", kwargs={"pk": creditor.pk}))

    assert "Test Creditor" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__creditor_detail_view__shows_archived_status(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_detail", kwargs={"pk": archived_creditor.pk}))

    content = response.content.decode()
    assert "Archived" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__creditor_detail_view__shows_delete_button_when_active(
    client: Client, creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_detail", kwargs={"pk": creditor.pk}))

    content = response.content.decode()
    assert "Delete" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__creditor_detail_view__shows_archive_button_when_active(
    client: Client, creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_detail", kwargs={"pk": creditor.pk}))

    content = response.content.decode()
    assert "Archive" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__creditor_detail_view__shows_restore_button_when_archived(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_detail", kwargs={"pk": archived_creditor.pk}))

    content = response.content.decode()
    assert "Restore" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__creditor_detail_view__hides_delete_button_when_archived(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_detail", kwargs={"pk": archived_creditor.pk}))

    content = response.content.decode()
    assert "Delete" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__edit_archived_creditor__loads_successfully(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_update", kwargs={"pk": archived_creditor.pk}))

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__request_delete_creditor__with_no_invoices__modal_shows_delete_enabled(
    client: Client, creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_request_delete", kwargs={"pk": creditor.pk}))

    assert response.status_code == 200
    assert response.context["can_delete"] is True
    content = response.content.decode()
    assert 'class="danger"' in content
    assert "disabled" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def _create_domain_invoice(creditor: Creditor) -> None:
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[],
    )
    repository.create(invoice)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__request_delete_creditor__with_invoices__modal_shows_blocking_reason(
    client: Client, creditor: Creditor
) -> None:
    _create_domain_invoice(creditor)

    response = client.get(reverse("invoices:creditor_request_delete", kwargs={"pk": creditor.pk}))

    assert response.status_code == 200
    assert response.context["can_delete"] is False
    assert len(response.context["blocking_reasons"]) > 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_creditor__with_no_invoices__deletes_and_redirects(
    client: Client, creditor: Creditor
) -> None:
    response = client.post(reverse("invoices:creditor_delete", kwargs={"pk": creditor.pk}))

    assert response.status_code == 200
    assert response["HX-Redirect"] == reverse("invoices:creditor_list")
    assert not Creditor.all_objects.filter(pk=creditor.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_creditor__with_invoices__fails_and_redirects(
    client: Client, creditor: Creditor
) -> None:
    _create_domain_invoice(creditor)

    response = client.post(reverse("invoices:creditor_delete", kwargs={"pk": creditor.pk}))

    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert Creditor.all_objects.filter(pk=creditor.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_creditor__archived__fails_and_redirects(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.post(reverse("invoices:creditor_delete", kwargs={"pk": archived_creditor.pk}))

    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert Creditor.all_objects.filter(pk=archived_creditor.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__archive_creditor__archives_and_redirects(client: Client, creditor: Creditor) -> None:
    response = client.post(reverse("invoices:creditor_archive", kwargs={"pk": creditor.pk}))

    assert response.status_code == 200
    assert "HX-Redirect" in response
    creditor.refresh_from_db()
    assert creditor.archived_at is not None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__archive_creditor__already_archived__rerenders_modal_with_error(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.post(
        reverse("invoices:creditor_archive", kwargs={"pk": archived_creditor.pk})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "already archived" in html
    assert "<dialog open>" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__restore_creditor__restores_and_redirects(
    client: Client, archived_creditor: Creditor
) -> None:
    response = client.post(
        reverse("invoices:creditor_restore", kwargs={"pk": archived_creditor.pk})
    )

    assert response.status_code == 200
    assert "HX-Redirect" in response
    archived_creditor.refresh_from_db()
    assert archived_creditor.archived_at is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__excludes_archived_by_default(
    client: Client, creditor: Creditor, archived_creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_list"))

    content = response.content.decode()
    assert_content_contains(content, creditor.name)
    assert_content_excludes(content, archived_creditor.name)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__includes_archived_when_requested(
    client: Client, creditor: Creditor, archived_creditor: Creditor
) -> None:
    response = client.get(reverse("invoices:creditor_list"), {"include_archived": "on"})

    content = response.content.decode()
    assert_content_contains(content, creditor.name, archived_creditor.name)

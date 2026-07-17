import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization
from tests import modelfactory


def assert_content_contains(content: str, *items: str) -> None:
    for item in items:
        assert item in content


def assert_content_excludes(content: str, *items: str) -> None:
    for item in items:
        assert item not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_detail_view__shows_funder_name(
    client: Client, funder: FundingOrganization
) -> None:
    response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": funder.pk}))

    assert "Test Funder" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_detail_view__shows_archived_status(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.get(
        reverse("fundingrequests:funder_detail", kwargs={"pk": archived_funder.pk})
    )

    assert "Archived" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_detail_view__shows_delete_button_when_active(
    client: Client, funder: FundingOrganization
) -> None:
    response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": funder.pk}))

    assert "Delete" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_detail_view__shows_archive_button_when_active(
    client: Client, funder: FundingOrganization
) -> None:
    response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": funder.pk}))

    assert "Archive" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_detail_view__shows_restore_button_when_archived(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.get(
        reverse("fundingrequests:funder_detail", kwargs={"pk": archived_funder.pk})
    )

    assert "Restore" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_detail_view__hides_delete_button_when_archived(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.get(
        reverse("fundingrequests:funder_detail", kwargs={"pk": archived_funder.pk})
    )

    assert "Delete" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__edit_archived_funder__loads_successfully(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.get(
        reverse("fundingrequests:funders_update", kwargs={"pk": archived_funder.pk})
    )

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__request_delete_funder__with_no_external_funding__modal_shows_delete_enabled(
    client: Client, funder: FundingOrganization
) -> None:
    response = client.get(
        reverse("fundingrequests:funder_request_delete", kwargs={"pk": funder.pk})
    )

    assert response.status_code == 200
    assert response.context["can_delete"] is True
    content = response.content.decode()
    assert 'class="danger"' in content
    assert "disabled" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__request_delete_funder__with_external_funding__modal_shows_blocking_reason(
    client: Client, funder: FundingOrganization
) -> None:
    funding_request = modelfactory.fundingrequest()
    ExternalFunding.objects.create(
        funding_request=funding_request,
        organization=funder,
        project_id="proj-1",
        project_name="Project 1",
    )

    response = client.get(
        reverse("fundingrequests:funder_request_delete", kwargs={"pk": funder.pk})
    )

    assert response.status_code == 200
    assert response.context["can_delete"] is False
    assert len(response.context["blocking_reasons"]) > 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_funder__with_no_external_funding__deletes_and_redirects(
    client: Client, funder: FundingOrganization
) -> None:
    response = client.post(reverse("fundingrequests:funder_delete", kwargs={"pk": funder.pk}))

    assert response.status_code == 200
    assert response["HX-Redirect"] == reverse("fundingrequests:funders")
    assert not FundingOrganization.all_objects.filter(pk=funder.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_funder__with_external_funding__fails_and_redirects(
    client: Client, funder: FundingOrganization
) -> None:
    funding_request = modelfactory.fundingrequest()
    ExternalFunding.objects.create(
        funding_request=funding_request,
        organization=funder,
        project_id="proj-1",
        project_name="Project 1",
    )

    response = client.post(reverse("fundingrequests:funder_delete", kwargs={"pk": funder.pk}))

    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert FundingOrganization.all_objects.filter(pk=funder.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_funder__archived__fails_and_redirects(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.post(
        reverse("fundingrequests:funder_delete", kwargs={"pk": archived_funder.pk})
    )

    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert FundingOrganization.all_objects.filter(pk=archived_funder.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__archive_funder__archives_and_redirects(
    client: Client, funder: FundingOrganization
) -> None:
    response = client.post(reverse("fundingrequests:funder_archive", kwargs={"pk": funder.pk}))

    assert response.status_code == 200
    assert "HX-Redirect" in response
    funder.refresh_from_db()
    assert funder.archived_at is not None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__archive_funder__already_archived__rerenders_modal_with_error(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.post(
        reverse("fundingrequests:funder_archive", kwargs={"pk": archived_funder.pk})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "already archived" in html
    assert "<dialog open>" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__restore_funder__restores_and_redirects(
    client: Client, archived_funder: FundingOrganization
) -> None:
    response = client.post(
        reverse("fundingrequests:funder_restore", kwargs={"pk": archived_funder.pk})
    )

    assert response.status_code == 200
    assert "HX-Redirect" in response
    archived_funder.refresh_from_db()
    assert archived_funder.archived_at is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__excludes_archived_by_default(
    client: Client, funder: FundingOrganization, archived_funder: FundingOrganization
) -> None:
    response = client.get(reverse("fundingrequests:funders"))

    content = response.content.decode()
    assert_content_contains(content, funder.name)
    assert_content_excludes(content, archived_funder.name)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__includes_archived_when_requested(
    client: Client, funder: FundingOrganization, archived_funder: FundingOrganization
) -> None:
    response = client.get(reverse("fundingrequests:funders"), {"include_archived": "on"})

    content = response.content.decode()
    assert_content_contains(content, funder.name, archived_funder.name)

"""Duplicate prevention for funding organizations: same name, case-insensitive."""

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import FundingOrganization


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_existing_name__case_insensitive__rejected(client: Client) -> None:
    FundingOrganization.objects.create(name="Deutsche Forschungsgemeinschaft")

    response = client.post(
        reverse("fundingrequests:funders_create"),
        {"name": "deutsche forschungsgemeinschaft"},
    )

    assert response.status_code == 200
    # rejected POST must not create anything: fixture DFG (1) + test-created DFG (1)
    assert (
        FundingOrganization.objects.filter(name__iexact="deutsche forschungsgemeinschaft").count()
        == 2
    )
    content = response.content.decode()
    assert "already exists" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_new_name__succeeds(client: Client) -> None:
    FundingOrganization.objects.create(name="Existing Foundation")

    client.post(
        reverse("fundingrequests:funders_create"),
        {"name": "Brand New Foundation"},
    )

    assert FundingOrganization.objects.filter(name="Brand New Foundation").exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_same_name_different_case__rejected(client: Client) -> None:
    FundingOrganization.objects.create(name="My Org")

    response = client.post(
        reverse("fundingrequests:funders_create"),
        {"name": "MY ORG"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "already exists" in content
    assert not FundingOrganization.objects.filter(name="MY ORG").exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funder_keeping_own_name__succeeds(client: Client) -> None:
    org = FundingOrganization.objects.create(name="My Org")

    client.post(
        reverse("fundingrequests:funders_update", kwargs={"pk": org.pk}),
        {"name": "my org"},  # same name, different case — must not count as duplicate of itself
    )

    org.refresh_from_db()
    assert org.name == "my org"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funder_to_other_funders_name__rejected(client: Client) -> None:
    org = FundingOrganization.objects.create(name="My Org")
    FundingOrganization.objects.create(name="Other Org")

    response = client.post(
        reverse("fundingrequests:funders_update", kwargs={"pk": org.pk}),
        {"name": "other org"},
    )

    org.refresh_from_db()
    assert org.name == "My Org"
    content = response.content.decode()
    assert "already exists" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__wizard_modal_create_with_existing_name__rejected(client: Client) -> None:
    FundingOrganization.objects.create(name="Existing Org")

    response = client.post(
        reverse("fundingrequests:funders_create_modal_submit"),
        {"name": "existing org"},
    )

    content = response.content.decode()
    assert "already exists" in content
    assert not FundingOrganization.objects.filter(
        name__iexact="existing org", name="existing org"
    ).exists()

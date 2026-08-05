"""Tests for automatic overlap detection."""

from collections.abc import Iterable
from typing import cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
from tests import modelfactory

_OVERLAP_ROR_URL = "https://ror.org/05a28rw58"


def create_link(org: FundingOrganization, type_name: str, value: str) -> FundingOrganizationLink:
    """Create a link for the given organisation, bypassing domain validation."""
    link_type = FundingOrganizationLinkType.objects.get(name=type_name)
    return FundingOrganizationLink.objects.create(
        funding_organization=org, type=link_type, value=value
    )


def update_from_ror(client: Client, pk: int) -> HttpResponse:
    return cast(
        HttpResponse,
        client.post(reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": pk})),
    )


def create_funding_organization(
    client: Client,
    name: str,
    *,
    link_type: str | None = None,
    link_value: str | None = None,
) -> HttpResponse:
    data: dict[str, object] = {"name": name}
    if link_type and link_value:
        data["link_type"] = [link_type]
        data["link_value"] = [link_value]
    return cast(HttpResponse, client.post(reverse("fundingrequests:funders_create"), data))


def update_funding_organization(
    client: Client,
    pk: int,
    name: str,
    *,
    link_type: str | None = None,
    link_value: str | None = None,
) -> HttpResponse:
    data: dict[str, object] = {"name": name}
    if link_type and link_value:
        data["link_type"] = [link_type]
        data["link_value"] = [link_value]
    return cast(
        HttpResponse,
        client.post(reverse("fundingrequests:funders_update", kwargs={"pk": pk}), data),
    )


def assert_overlap_dialog(response: HttpResponse, *org_names: str) -> None:
    """Assert the response contains the overlap dialog with the expected org names."""
    content = response.content.decode()
    assert "Duplicate Organization Detected" in content
    assert "Merge" in content
    for name in org_names:
        assert name in content


def assert_no_overlap_dialog(response: HttpResponse) -> None:
    """Assert the response does not contain the overlap dialog."""
    assert "Duplicate Organization Detected" not in response.content.decode()


def assert_redirect(response: HttpResponse) -> None:
    assert response.status_code == 302


def overlapping_org_fixture(
    *names: str,
) -> Iterable[FundingOrganization]:
    """Yield organisations that share ``_OVERLAP_ROR_URL``."""
    return [modelfactory.funding_organization(name=n) for n in names]


# ── ROR update overlap detection ──────────────────────────────────────


class BaseTestAutomaticOverlapDetection:
    def test__update_from_ror__shows_overlap_dialog_when_overlaps_found(
        self, client: Client
    ) -> None:
        org1, org2 = overlapping_org_fixture("Org 1", "Org 2")
        create_link(org1, "ROR", _OVERLAP_ROR_URL)
        create_link(org2, "ROR", _OVERLAP_ROR_URL)

        response = update_from_ror(client, org1.pk)

        assert_overlap_dialog(response, "Org 2")

    def test__update_from_ror__no_dialog_when_no_overlaps(self, client: Client) -> None:
        org = modelfactory.funding_organization(name="Unique Org")

        response = update_from_ror(client, org.pk)

        assert_no_overlap_dialog(response)

    def test__update_from_ror__dialog_has_dismiss_button(self, client: Client) -> None:
        org1, _ = overlapping_org_fixture("Org 1", "Org 2")
        create_link(org1, "ROR", _OVERLAP_ROR_URL)
        create_link(modelfactory.funding_organization(name="Org 2"), "ROR", _OVERLAP_ROR_URL)

        response = update_from_ror(client, org1.pk)

        content = response.content.decode()
        assert "Dismiss" in content

    def test__update_from_ror__dialog_has_merge_buttons(self, client: Client) -> None:
        org1, org2 = overlapping_org_fixture("Org 1", "Org 2")
        create_link(org1, "ROR", _OVERLAP_ROR_URL)
        create_link(org2, "ROR", _OVERLAP_ROR_URL)

        response = update_from_ror(client, org1.pk)

        content = response.content.decode()
        assert f"Merge into {org2.name}" in content

    def test__update_from_ror__shows_overlap_dialog_even_when_no_links_changed(
        self, client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        org1, org2 = overlapping_org_fixture("Org 1", "Org 2")
        create_link(org1, "ROR", _OVERLAP_ROR_URL)
        create_link(org2, "ROR", _OVERLAP_ROR_URL)

        def mock_update(*args: object, **kwargs: object) -> bool:
            return False

        monkeypatch.setattr(
            "coda.apps.fundingrequests.views.funders.update_funder_from_ror",
            mock_update,
        )

        response = update_from_ror(client, org1.pk)

        assert_overlap_dialog(response, "Org 2")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestAutomaticOverlapDetection(BaseTestAutomaticOverlapDetection):
    """Tests for automatic overlap detection after ROR update."""

    pass


# ── Update form overlap detection ─────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestOverlapDetectionOnUpdateForm:
    """Overlap detection should also run when updating an org via the standard form."""

    def test__update_form__shows_overlap_dialog_when_overlaps_found(self, client: Client) -> None:
        existing = modelfactory.funding_organization(name="Existing Org")
        create_link(existing, "ROR", _OVERLAP_ROR_URL)

        target = modelfactory.funding_organization(name="Target Org")
        response = update_funding_organization(
            client,
            target.pk,
            "Target Org",
            link_type="ROR",
            link_value=_OVERLAP_ROR_URL,
        )

        assert_overlap_dialog(response, "Existing Org")

    def test__update_form__redirects_when_no_overlaps(self, client: Client) -> None:
        org = modelfactory.funding_organization(name="Unique Org")

        response = update_funding_organization(client, org.pk, "Unique Org")

        assert_redirect(response)


# ── Create form overlap detection ─────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestOverlapDetectionOnCreateForm:
    """Overlap detection should also run when creating a new org via the create form."""

    def test__create_form__shows_overlap_dialog_when_new_org_matches_existing(
        self, client: Client
    ) -> None:
        existing = modelfactory.funding_organization(name="Existing Org")
        create_link(existing, "ROR", _OVERLAP_ROR_URL)

        response = create_funding_organization(
            client, "New Org", link_type="ROR", link_value=_OVERLAP_ROR_URL
        )

        assert_overlap_dialog(response, "Existing Org")

    def test__create_form__redirects_when_no_overlaps(self, client: Client) -> None:
        response = create_funding_organization(client, "Unique New Org")

        assert_redirect(response)

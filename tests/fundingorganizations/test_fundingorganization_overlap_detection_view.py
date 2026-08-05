"""Tests for automatic overlap detection after ROR update."""

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
from tests import modelfactory

_OVERLAP_ROR_URL = "https://ror.org/05a28rw58"


def _create_overlapping_ror_orgs() -> tuple[FundingOrganization, FundingOrganization]:
    org1 = modelfactory.funding_organization(name="Org 1")
    org2 = modelfactory.funding_organization(name="Org 2")
    ror_type = FundingOrganizationLinkType.objects.get(name="ROR")
    FundingOrganizationLink.objects.create(
        funding_organization=org1, type=ror_type, value=_OVERLAP_ROR_URL
    )
    FundingOrganizationLink.objects.create(
        funding_organization=org2, type=ror_type, value=_OVERLAP_ROR_URL
    )
    return org1, org2


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestAutomaticOverlapDetection:
    """Tests for automatic overlap detection after ROR update."""

    def test__update_from_ror__shows_overlap_dialog_when_overlaps_found(
        self, client: Client
    ) -> None:
        """Should show overlap dialog when overlapping organizations are found."""
        org1, org2 = _create_overlapping_ror_orgs()

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        content = response.content.decode()
        assert "Duplicate Organization Detected" in content
        assert "Org 2" in content
        assert "Merge" in content

    def test__update_from_ror__no_dialog_when_no_overlaps(self, client: Client) -> None:
        """Should not show overlap dialog when no overlapping organizations are found."""
        org = modelfactory.funding_organization(name="Unique Org")

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk})
        )

        content = response.content.decode()
        assert "Duplicate Organization Detected" not in content

    def test__update_from_ror__dialog_has_dismiss_button(self, client: Client) -> None:
        """Should have a dismiss button in the overlap dialog."""
        org1, _org2 = _create_overlapping_ror_orgs()

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        content = response.content.decode()
        assert "Dismiss" in content

    def test__update_from_ror__dialog_has_merge_buttons(self, client: Client) -> None:
        """Should have merge buttons for each overlapping organization."""
        org1, org2 = _create_overlapping_ror_orgs()

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        content = response.content.decode()
        assert f"Merge into {org2.name}" in content

    def test__update_from_ror__shows_overlap_dialog_even_when_no_links_changed(
        self, client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Overlap detection should run regardless of whether the ROR update
        actually changed any links. Two orgs may already share identifiers;
        that overlap exists whether or not the update mutated anything."""
        org1, org2 = _create_overlapping_ror_orgs()

        def mock_update(*args: object, **kwargs: object) -> bool:
            return False  # Simulate: ROR update didn't change any links

        monkeypatch.setattr(
            "coda.apps.fundingrequests.views.funders.update_funder_from_ror",
            mock_update,
        )

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        content = response.content.decode()
        assert "Duplicate Organization Detected" in content
        assert "Org 2" in content
        assert "Merge" in content

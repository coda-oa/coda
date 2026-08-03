"""Tests for automatic overlap detection after ROR update."""

import pytest
from django.test import Client
from django.urls import reverse

from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestAutomaticOverlapDetection:
    """Tests for automatic overlap detection after ROR update."""

    def test__update_from_ror__shows_overlap_dialog_when_overlaps_found(
        self, client: Client
    ) -> None:
        """Should show overlap dialog when overlapping organizations are found."""
        # Create two organizations with the same ROR link
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")

        # Add the same ROR link to both organizations
        from coda.apps.fundingrequests.models import FundingOrganizationLinkType

        ror_type = FundingOrganizationLinkType.objects.get(name="ROR")
        from coda.apps.fundingrequests.models import FundingOrganizationLink

        FundingOrganizationLink.objects.create(
            funding_organization=org1,
            type=ror_type,
            value="https://ror.org/05a28rw58",
        )
        FundingOrganizationLink.objects.create(
            funding_organization=org2,
            type=ror_type,
            value="https://ror.org/05a28rw58",
        )

        # Update org1 from ROR (this should trigger overlap detection)
        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        # The response should contain the overlap dialog
        content = response.content.decode()
        assert "Duplicate Organization Detected" in content
        assert "Org 2" in content
        assert "Merge" in content

    def test__update_from_ror__no_dialog_when_no_overlaps(self, client: Client) -> None:
        """Should not show overlap dialog when no overlapping organizations are found."""
        org = modelfactory.funding_organization(name="Unique Org")

        # Update org from ROR (no overlaps should be found)
        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk})
        )

        # The response should not contain the overlap dialog
        content = response.content.decode()
        assert "Duplicate Organization Detected" not in content

    def test__update_from_ror__dialog_has_dismiss_button(self, client: Client) -> None:
        """Should have a dismiss button in the overlap dialog."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")

        from coda.apps.fundingrequests.models import FundingOrganizationLinkType

        ror_type = FundingOrganizationLinkType.objects.get(name="ROR")
        from coda.apps.fundingrequests.models import FundingOrganizationLink

        FundingOrganizationLink.objects.create(
            funding_organization=org1,
            type=ror_type,
            value="https://ror.org/05a28rw58",
        )
        FundingOrganizationLink.objects.create(
            funding_organization=org2,
            type=ror_type,
            value="https://ror.org/05a28rw58",
        )

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        content = response.content.decode()
        assert "Dismiss" in content

    def test__update_from_ror__dialog_has_merge_buttons(self, client: Client) -> None:
        """Should have merge buttons for each overlapping organization."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")

        from coda.apps.fundingrequests.models import FundingOrganizationLinkType

        ror_type = FundingOrganizationLinkType.objects.get(name="ROR")
        from coda.apps.fundingrequests.models import FundingOrganizationLink

        FundingOrganizationLink.objects.create(
            funding_organization=org1,
            type=ror_type,
            value="https://ror.org/05a28rw58",
        )
        FundingOrganizationLink.objects.create(
            funding_organization=org2,
            type=ror_type,
            value="https://ror.org/05a28rw58",
        )

        response = client.post(
            reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org1.pk})
        )

        content = response.content.decode()
        # Check that there's a merge button for org2
        assert "Merge into Org 2" in content

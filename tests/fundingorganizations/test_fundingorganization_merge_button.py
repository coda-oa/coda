"""Tests for the merge button on funding organization detail page."""

import pytest
from django.test import Client
from django.urls import reverse

from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestMergeButtonOnDetailPage:
    """Tests for the merge button on funding organization detail page."""

    def test__detail_page__shows_merge_button_for_active_organization(self, client: Client) -> None:
        """Should show merge button for active (non-archived) organizations."""
        org = modelfactory.funding_organization(name="Test Org")
        response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk}))
        content = response.content.decode()
        assert "Merge into..." in content

    def test__detail_page__hides_merge_button_for_archived_organization(
        self, client: Client
    ) -> None:
        """Should hide merge button for archived organizations."""
        org = modelfactory.funding_organization(name="Test Org")
        org.archive()

        response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk}))
        content = response.content.decode()
        assert "Merge into..." not in content

    def test__detail_page__merge_button_has_correct_htmx_attributes(self, client: Client) -> None:
        """Should have correct HTMX attributes for loading target search page."""
        org = modelfactory.funding_organization(name="Test Org")
        response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk}))
        content = response.content.decode()

        # Check that the merge button has the correct HTMX attributes
        assert "hx-get" in content
        assert "Merge into..." in content
        # The button should link to the select-target page
        select_target_url = reverse(
            "fundingrequests:funder_merge_select_target", kwargs={"pk": org.pk}
        )
        assert select_target_url in content

    def test__detail_page__merge_button_is_in_action_area(self, client: Client) -> None:
        """Should be in the action area alongside Edit button."""
        org = modelfactory.funding_organization(name="Test Org")
        response = client.get(reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk}))
        content = response.content.decode()

        # Check that both Edit and Merge into... buttons are present
        assert "Edit" in content
        assert "Merge into..." in content

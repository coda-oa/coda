import re

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import FundingOrganization
from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestMergeFunderSelectTarget:
    """Tests for the merge target selection view."""

    def test__select_target__returns_200(self, client: Client) -> None:
        """Should return 200 when accessing the select target page."""
        source = modelfactory.funding_organization(name="Source Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
        )
        assert response.status_code == 200

    def test__select_target__renders_dialog(self, client: Client) -> None:
        """Should render a dialog element, not a full page."""
        source = modelfactory.funding_organization(name="Source Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
        )
        content = response.content.decode()
        assert "<dialog open>" in content
        assert "{% extends" not in content

    def test__select_target__has_close_button(self, client: Client) -> None:
        """Should have a close button that removes the dialog."""
        source = modelfactory.funding_organization(name="Source Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
        )
        content = response.content.decode()
        assert "onclick=\"this.closest('dialog').remove()\"" in content

    def test__select_target__has_htmx_search_form(self, client: Client) -> None:
        """Should have a form with HTMX attributes for search within dialog."""
        source = modelfactory.funding_organization(name="Source Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
        )
        content = response.content.decode()
        assert 'hx-target="closest dialog"' in content
        assert 'hx-swap="innerHTML"' in content

    def test__select_target__shows_source_organization_name(self, client: Client) -> None:
        """Should show the source organization name."""
        source = modelfactory.funding_organization(name="Source Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
        )
        content = response.content.decode()
        assert "Source Org" in content

    def test__select_target__excludes_source_from_search_results(self, client: Client) -> None:
        """Should exclude the source organization from search results."""
        source = modelfactory.funding_organization(name="Source Org")
        modelfactory.funding_organization(name="Target Org")

        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
            + "?query=Org"
        )
        content = response.content.decode()
        assert "Target Org" in content
        # Source should not appear in search results (only in the dialog title)
        assert content.count("<td>Source Org</td>") == 0

    def test__select_target__excludes_archived_organizations(self, client: Client) -> None:
        """Should exclude archived organizations from search results."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")
        target.archive()

        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
            + "?query=Org"
        )
        content = response.content.decode()
        assert not re.search(r"<td>Target Org</td>", content)

    def test__select_target__no_query_returns_full_dialog(self, client: Client) -> None:
        """Initial load (no query) should return the full dialog wrapper."""
        source = modelfactory.funding_organization(name="Source Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
        )
        content = response.content.decode()
        assert "<dialog open>" in content

    def test__select_target__with_query_returns_content_only(self, client: Client) -> None:
        """Search request (with query) should return content without the dialog wrapper."""
        source = modelfactory.funding_organization(name="Source Org")
        modelfactory.funding_organization(name="Target Org")
        response = client.get(
            reverse("fundingrequests:funder_merge_select_target", kwargs={"pk": source.pk})
            + "?query=Org"
        )
        content = response.content.decode()
        assert "<dialog open>" not in content
        assert "Target Org" in content
        assert 'hx-target="closest dialog"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestMergeFunderPreview:
    """Tests for the merge preview view."""

    def test__preview__returns_200(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should return 200 when accessing the merge preview page."""
        source, target = source_target_orgs
        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        assert response.status_code == 200

    def test__preview__shows_source_organization(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should show the source organization."""
        source, target = source_target_orgs
        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        content = response.content.decode()
        assert "Source Org" in content

    def test__preview__shows_target_organization(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should show the target organization."""
        source, target = source_target_orgs
        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        content = response.content.decode()
        assert "Target Org" in content

    def test__preview__shows_affected_funding_requests(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should show affected funding requests."""
        source, target = source_target_orgs
        modelfactory.external_funding(funder_id=source.pk)

        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        content = response.content.decode()
        assert "Related Funding Requests" in content

    def test__preview__shows_both_source_and_target_funding_requests(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should show funding requests from both source and target organizations."""
        source, target = source_target_orgs
        source_record = modelfactory.external_funding(funder_id=source.pk)
        target_record = modelfactory.external_funding(funder_id=target.pk)

        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        content = response.content.decode()
        assert source_record.project_name in content
        assert target_record.project_name in content

    def test__preview__shows_correct_count_of_funding_requests(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should show correct count of all funding requests from both orgs."""
        source, target = source_target_orgs
        modelfactory.external_funding(funder_id=source.pk)
        modelfactory.external_funding(funder_id=source.pk)
        modelfactory.external_funding(funder_id=target.pk)

        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        assert response.context["affected_records"].count() == 3

    def test__preview__shows_confirm_merge_button(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should show the confirm merge button."""
        source, target = source_target_orgs
        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        content = response.content.decode()
        assert "Confirm Merge" in content

    def test__preview__returns_redirect_for_archived_source(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should return redirect for archived source organization."""
        source, target = source_target_orgs
        source.archive()

        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response

    def test__preview__returns_redirect_for_archived_target(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should return redirect for archived target organization."""
        source, target = source_target_orgs
        target.archive()

        response = client.get(
            reverse(
                "fundingrequests:funder_merge_preview",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
class TestMergeFunderExecute:
    """Tests for the merge execution view."""

    def test__execute__merges_organizations(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should merge the organizations."""
        source, target = source_target_orgs
        source_pk = source.pk

        response = client.post(
            reverse(
                "fundingrequests:funder_merge_execute",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )

        assert response.status_code == 200
        assert not FundingOrganization.all_objects.filter(pk=source_pk).exists()

    def test__execute__redirects_to_target_detail(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should redirect to the target's detail page."""
        source, target = source_target_orgs

        response = client.post(
            reverse(
                "fundingrequests:funder_merge_execute",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )

        expected_url = reverse("fundingrequests:funder_detail", kwargs={"pk": target.pk})
        assert response["HX-Redirect"] == expected_url

    def test__execute__returns_redirect_for_archived_source(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should return redirect for archived source organization."""
        source, target = source_target_orgs
        source.archive()

        response = client.post(
            reverse(
                "fundingrequests:funder_merge_execute",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response
        assert FundingOrganization.all_objects.filter(pk=source.pk).exists()

    def test__execute__returns_redirect_for_archived_target(
        self,
        client: Client,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """Should return redirect for archived target organization."""
        source, target = source_target_orgs
        target.archive()

        response = client.post(
            reverse(
                "fundingrequests:funder_merge_execute",
                kwargs={"pk": source.pk, "target_pk": target.pk},
            )
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response
        assert FundingOrganization.all_objects.filter(pk=source.pk).exists()

    def test__execute__returns_error_for_same_organization(self, client: Client) -> None:
        """Should return error when trying to merge an organization into itself."""
        org = modelfactory.funding_organization(name="Same Org")

        response = client.post(
            reverse(
                "fundingrequests:funder_merge_execute",
                kwargs={"pk": org.pk, "target_pk": org.pk},
            )
        )

        assert response.status_code == 200
        assert FundingOrganization.all_objects.filter(pk=org.pk).exists()

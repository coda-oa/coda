import pytest

from coda.apps.fundingrequests.services.funder_services import search_organizations_for_merge
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId
from tests import modelfactory
from tests.fundingorganizations.conftest import VALID_ROR_ID


@pytest.mark.django_db
class TestSearchOrganizationsForMerge:
    """Tests for searching organizations for merge target."""

    def test__search__returns_organizations_matching_name(self) -> None:
        """Should find organizations with matching name."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="University of Example")

        results = search_organizations_for_merge("University", exclude_pk=org1.pk)

        assert len(results) == 1
        assert results[0].pk == org2.pk

    def test__search__returns_organizations_matching_ror(self) -> None:
        """Should find organizations with matching ROR link."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org2.set_links([Ror(VALID_ROR_ID)])

        results = search_organizations_for_merge(VALID_ROR_ID, exclude_pk=org1.pk)

        assert len(results) == 1
        assert results[0].pk == org2.pk

    def test__search__returns_organizations_matching_crossref(self) -> None:
        """Should find organizations with matching Crossref link."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org2.set_links([CrossrefId("12345")])

        results = search_organizations_for_merge("12345", exclude_pk=org1.pk)

        assert len(results) == 1
        assert results[0].pk == org2.pk

    def test__search__excludes_specified_organization(self) -> None:
        """Should exclude the specified organization from results."""
        org1 = modelfactory.funding_organization(name="University of Example")
        org2 = modelfactory.funding_organization(name="Another University")

        results = search_organizations_for_merge("University", exclude_pk=org1.pk)

        assert len(results) == 1
        assert results[0].pk == org2.pk

    def test__search__excludes_archived_organizations(self) -> None:
        """Should exclude archived organizations from results."""
        from django.utils import timezone

        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org2.archived_at = timezone.now()
        org2.save()

        results = search_organizations_for_merge("Org", exclude_pk=org1.pk)

        assert len(results) == 0

    def test__search__returns_empty_list_when_no_matches(self) -> None:
        """Should return empty list when no organizations match."""
        org1 = modelfactory.funding_organization(name="Org 1")

        results = search_organizations_for_merge("Nonexistent", exclude_pk=org1.pk)

        assert len(results) == 0

    def test__search__is_case_insensitive(self) -> None:
        """Should be case insensitive when searching by name."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="University of Example")

        results = search_organizations_for_merge("university", exclude_pk=org1.pk)

        assert len(results) == 1
        assert results[0].pk == org2.pk

    def test__search__returns_multiple_results(self) -> None:
        """Should return multiple matching organizations."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="University of Example")
        org3 = modelfactory.funding_organization(name="Another University")

        results = search_organizations_for_merge("University", exclude_pk=org1.pk)

        assert len(results) == 2
        result_pks = {r.pk for r in results}
        assert org2.pk in result_pks
        assert org3.pk in result_pks

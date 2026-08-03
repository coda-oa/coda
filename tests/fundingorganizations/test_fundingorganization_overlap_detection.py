import pytest

from coda.apps.fundingrequests.services.funder_services import find_overlapping_organizations
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId
from tests import modelfactory

# Valid ROR IDs with correct checksums
VALID_ROR_ID = "https://ror.org/04pz7b180"
VALID_ROR_ID_2 = "https://ror.org/03yrm5c26"


@pytest.mark.django_db
class TestFindOverlappingOrganizations:
    """Tests for finding organizations with overlapping identifiers."""

    def test__find_overlapping__returns_organizations_with_matching_ror(self) -> None:
        """Should find organizations with matching ROR links."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org1.set_links([Ror(VALID_ROR_ID)])
        org2.set_links([Ror(VALID_ROR_ID)])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 1
        assert overlapping[0].pk == org2.pk

    def test__find_overlapping__returns_organizations_with_matching_crossref(self) -> None:
        """Should find organizations with matching Crossref links."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org1.set_links([CrossrefId("12345")])
        org2.set_links([CrossrefId("12345")])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 1
        assert overlapping[0].pk == org2.pk

    def test__find_overlapping__excludes_current_organization(self) -> None:
        """Should exclude the current organization from results."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org1.set_links([Ror(VALID_ROR_ID)])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 0

    def test__find_overlapping__excludes_archived_organizations(self) -> None:
        """Should exclude archived organizations from results."""
        from django.utils import timezone

        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org2.archived_at = timezone.now()
        org2.save()
        org1.set_links([Ror(VALID_ROR_ID)])
        org2.set_links([Ror(VALID_ROR_ID)])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 0

    def test__find_overlapping__returns_multiple_overlapping_organizations(self) -> None:
        """Should return all overlapping organizations."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org3 = modelfactory.funding_organization(name="Org 3")
        org1.set_links([Ror(VALID_ROR_ID)])
        org2.set_links([Ror(VALID_ROR_ID)])
        org3.set_links([Ror(VALID_ROR_ID)])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 2
        overlapping_pks = {o.pk for o in overlapping}
        assert org2.pk in overlapping_pks
        assert org3.pk in overlapping_pks

    def test__find_overlapping__returns_empty_list_when_no_overlaps(self) -> None:
        """Should return empty list when no organizations have matching links."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org1.set_links([Ror(VALID_ROR_ID)])
        org2.set_links([Ror(VALID_ROR_ID_2)])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 0

    def test__find_overlapping__returns_empty_list_when_no_links(self) -> None:
        """Should return empty list when organization has no links."""
        org1 = modelfactory.funding_organization(name="Org 1")
        org2 = modelfactory.funding_organization(name="Org 2")
        org2.set_links([Ror(VALID_ROR_ID)])

        overlapping = find_overlapping_organizations(org1)

        assert len(overlapping) == 0

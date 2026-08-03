import pytest
from django.utils import timezone
from collections.abc import Iterable

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.services.funder_services import merge_funding_organizations
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId
from coda.domain.publication.links import Link
from tests import modelfactory

# Valid ROR ID with correct checksum
VALID_ROR_ID = "https://ror.org/04pz7b180"
VALID_ROR_ID_2 = "https://ror.org/03yrm5c26"


@pytest.mark.django_db
class TestMergeFundingOrganizations:
    """Tests for merging two funding organizations."""

    def test__merge__moves_external_funding_records_to_target(self) -> None:
        """When merging, all ExternalFunding records should move from source to target."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")
        external_funding = modelfactory.external_funding(funder_id=source.pk)

        merge_funding_organizations(source, target)

        external_funding.refresh_from_db()
        assert external_funding.organization_id == target.pk

    def test__merge__merges_links_from_source_to_target(self) -> None:
        """When merging, links from source should be merged into target."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")
        source.set_links([Ror(VALID_ROR_ID), CrossrefId("12345")])
        target.set_links([Ror(VALID_ROR_ID_2)])

        merge_funding_organizations(source, target)

        target.refresh_from_db()
        target_links = target.get_links()
        # Target's ROR link should take priority
        assert Ror(VALID_ROR_ID_2) in target_links
        # Source's CrossrefId should be added
        assert CrossrefId("12345") in target_links

    def test__merge__deletes_source_organization(self) -> None:
        """When merging, the source organization should be deleted."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")
        source_pk = source.pk

        merge_funding_organizations(source, target)

        assert not FundingOrganization.all_objects.filter(pk=source_pk).exists()

    def test__merge__keeps_target_name(self) -> None:
        """When merging, the target organization should keep its name."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")

        merge_funding_organizations(source, target)

        target.refresh_from_db()
        assert target.name == "Target Org"

    def test__merge__raises_error_when_source_equals_target(self) -> None:
        """Merging an organization into itself should raise ValueError."""
        org = modelfactory.funding_organization(name="Same Org")

        with pytest.raises(ValueError, match="Cannot merge organization into itself"):
            merge_funding_organizations(org, org)

    def test__merge__raises_error_when_source_is_archived(self) -> None:
        """Merging an archived organization should raise ValueError."""
        source = modelfactory.funding_organization(name="Archived Org")
        source.archived_at = timezone.now()
        source.save()
        target = modelfactory.funding_organization(name="Target Org")

        with pytest.raises(ValueError, match="Cannot merge an archived organization"):
            merge_funding_organizations(source, target)

    def test__merge__raises_error_when_target_is_archived(self) -> None:
        """Merging into an archived organization should raise ValueError."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Archived Org")
        target.archived_at = timezone.now()
        target.save()

        with pytest.raises(ValueError, match="Cannot merge into an archived organization"):
            merge_funding_organizations(source, target)

    def test__merge__is_atomic(self) -> None:
        """When merging, all operations should be atomic (all-or-nothing)."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")
        source.set_links([Ror(VALID_ROR_ID)])
        source_pk = source.pk
        target_pk = target.pk

        # Simulate an error during merge by raising an exception
        # The merge should roll back all changes
        original_set_links = FundingOrganization.set_links

        def failing_set_links(self: FundingOrganization, links: Iterable[Link]) -> None:
            if self.pk == target_pk:
                raise Exception("Simulated error")
            return original_set_links(self, links)

        import unittest.mock

        with unittest.mock.patch.object(FundingOrganization, "set_links", failing_set_links):
            with pytest.raises(Exception, match="Simulated error"):
                merge_funding_organizations(source, target)

        # Source should still exist (rollback)
        assert FundingOrganization.all_objects.filter(pk=source_pk).exists()
        # Target should not have any links (rollback)
        target.refresh_from_db()
        assert len(target.get_links()) == 0

import pytest

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.services.funder_services import merge_funding_organizations
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId
from tests import modelfactory
from tests.fundingorganizations.conftest import VALID_ROR_ID, VALID_ROR_ID_2


@pytest.mark.django_db
class TestMergeFundingOrganizations:
    """Tests for merging two funding organizations."""

    def test__merge__moves_external_funding_records_to_target(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When merging, all ExternalFunding records should move from source to target."""
        source, target = source_target_orgs
        external_funding = modelfactory.external_funding(funder_id=source.pk)

        merge_funding_organizations(source, target)

        external_funding.refresh_from_db()
        assert external_funding.organization_id == target.pk

    def test__merge__merges_links_from_source_to_target(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When merging, links from source should be merged into target."""
        source, target = source_target_orgs
        source.set_links([Ror(VALID_ROR_ID), CrossrefId("12345")])
        target.set_links([Ror(VALID_ROR_ID_2)])

        merge_funding_organizations(source, target)

        target.refresh_from_db()
        target_links = target.get_links()
        # Target's ROR link should take priority
        assert Ror(VALID_ROR_ID_2) in target_links
        # Source's CrossrefId should be added
        assert CrossrefId("12345") in target_links

    def test__merge__deletes_source_organization(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When merging, the source organization should be deleted."""
        source, target = source_target_orgs
        source_pk = source.pk

        merge_funding_organizations(source, target)

        assert not FundingOrganization.all_objects.filter(pk=source_pk).exists()

    def test__merge__keeps_target_name(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When merging, the target organization should keep its name."""
        source, target = source_target_orgs

        merge_funding_organizations(source, target)

        target.refresh_from_db()
        assert target.name == "Target Org"

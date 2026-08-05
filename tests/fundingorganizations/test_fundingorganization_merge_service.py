import pytest

from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization
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

    def test__merge__deduplicates_external_funding_when_source_and_target_share_same_funding_request_with_same_project_id(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When both source and target have ExternalFunding records for the same funding request
        with the same project_id, the merge should deduplicate (only keep one)."""
        source, target = source_target_orgs
        funding_request = modelfactory.fundingrequest()

        ExternalFunding.objects.create(
            funding_request=funding_request,
            organization=source,
            project_id="PROJ-001",
            project_name="Grant A",
        )
        ExternalFunding.objects.create(
            funding_request=funding_request,
            organization=target,
            project_id="PROJ-001",
            project_name="Grant A",
        )

        merge_funding_organizations(source, target)

        remaining = ExternalFunding.objects.filter(
            funding_request=funding_request,
            organization=target,
            project_id="PROJ-001",
        )
        assert remaining.count() == 1

    def test__merge__keeps_external_funding_with_different_project_ids_on_same_funding_request(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When source and target each fund the same request via different grants
        (different project_id), the merge should keep both — they're distinct."""
        source, target = source_target_orgs
        funding_request = modelfactory.fundingrequest()

        ExternalFunding.objects.create(
            funding_request=funding_request,
            organization=source,
            project_id="PROJ-001",
            project_name="Grant A",
        )
        ExternalFunding.objects.create(
            funding_request=funding_request,
            organization=target,
            project_id="PROJ-002",
            project_name="Grant B",
        )

        merge_funding_organizations(source, target)

        remaining = ExternalFunding.objects.filter(
            funding_request=funding_request,
            organization=target,
        )
        assert remaining.count() == 2

    def test__merge__handles_mixed_shared_and_unique_external_funding(
        self,
        source_target_orgs: tuple[FundingOrganization, FundingOrganization],
    ) -> None:
        """When source and target share some ExternalFunding records but also have unique ones,
        merge should deduplicate shared ones and keep unique ones."""
        source, target = source_target_orgs
        fr1 = modelfactory.fundingrequest()
        fr2 = modelfactory.fundingrequest()

        # fr1: both orgs fund it with SAME project_id (should deduplicate)
        ExternalFunding.objects.create(
            funding_request=fr1,
            organization=source,
            project_id="SHARED",
            project_name="Shared Project",
        )
        ExternalFunding.objects.create(
            funding_request=fr1,
            organization=target,
            project_id="SHARED",
            project_name="Shared Project",
        )
        # fr2: only source funds it (should move normally)
        ExternalFunding.objects.create(
            funding_request=fr2,
            organization=source,
            project_id="UNIQUE",
            project_name="Unique Project",
        )

        merge_funding_organizations(source, target)

        assert ExternalFunding.objects.filter(organization_id=target.pk).count() == 2
        assert not ExternalFunding.objects.filter(organization_id=source.pk).exists()

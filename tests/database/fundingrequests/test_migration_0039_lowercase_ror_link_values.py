import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestLowercaseRorLinkValues(MigratorTestCase):
    """ROR identifiers persisted with uppercase letters are canonicalized."""

    migrate_from = ("fundingrequests", "0038_collapse_duplicate_labels")
    migrate_to = ("fundingrequests", "0039_lowercase_ror_link_values")

    def prepare(self) -> None:
        FundingOrganization = self.old_state.apps.get_model(
            "fundingrequests", "FundingOrganization"
        )
        LinkType = self.old_state.apps.get_model("fundingrequests", "FundingOrganizationLinkType")
        Link = self.old_state.apps.get_model("fundingrequests", "FundingOrganizationLink")

        organization = FundingOrganization.objects.create(name="Uppercase ROR")
        ror_type, _ = LinkType.objects.get_or_create(name="ROR")
        doi_type, _ = LinkType.objects.get_or_create(name="DOI")
        Link.objects.create(
            funding_organization=organization,
            type=ror_type,
            value="https://ror.org/02MHBDp94",
        )
        Link.objects.create(
            funding_organization=organization,
            type=doi_type,
            value="10.1234/UPPER",
        )
        self.organization_pk = organization.pk

    def test__ror_values_are_lowercased__other_links_untouched(self) -> None:
        Link = self.new_state.apps.get_model("fundingrequests", "FundingOrganizationLink")

        values = dict(
            Link.objects.filter(funding_organization_id=self.organization_pk).values_list(
                "type__name", "value"
            )
        )
        assert values["ROR"] == "https://ror.org/02mhbdp94"
        assert values["DOI"] == "10.1234/UPPER"

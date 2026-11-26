import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestLowercaseRorLinkValues(MigratorTestCase):
    """ROR identifiers persisted with uppercase letters are canonicalized."""

    migrate_from = ("institutions", "0010_alter_institutionlinktype_options")
    migrate_to = ("institutions", "0011_lowercase_ror_link_values")

    def prepare(self) -> None:
        Institution = self.old_state.apps.get_model("institutions", "Institution")
        LinkType = self.old_state.apps.get_model("institutions", "InstitutionLinkType")
        Link = self.old_state.apps.get_model("institutions", "InstitutionLink")

        institution = Institution.objects.create(name="Uppercase ROR")
        ror_type = LinkType.objects.create(name="ROR")
        isni_type = LinkType.objects.create(name="ISNI")
        Link.objects.create(
            institution=institution,
            type=ror_type,
            value="https://ror.org/02MHBDp94",
        )
        Link.objects.create(
            institution=institution,
            type=isni_type,
            value="000000012103268X",
        )
        self.institution_pk = institution.pk

    def test__ror_values_are_lowercased__other_links_untouched(self) -> None:
        Link = self.new_state.apps.get_model("institutions", "InstitutionLink")

        values = dict(
            Link.objects.filter(institution_id=self.institution_pk).values_list(
                "type__name", "value"
            )
        )
        assert values["ROR"] == "https://ror.org/02mhbdp94"
        assert values["ISNI"] == "000000012103268X"

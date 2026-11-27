import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestRenameRingoldLinkType(MigratorTestCase):
    """Without a "Ringgold" row, the "Ringold" typo row is renamed in place."""

    migrate_from = ("institutions", "0008_remove_path_and_node_id")
    migrate_to = ("institutions", "0009_rename_ringold_link_type")

    def prepare(self) -> None:
        Institution = self.old_state.apps.get_model("institutions", "Institution")
        InstitutionLinkType = self.old_state.apps.get_model("institutions", "InstitutionLinkType")
        InstitutionLink = self.old_state.apps.get_model("institutions", "InstitutionLink")

        institution = Institution.objects.create(name="Typo Institution")
        typo_type = InstitutionLinkType.objects.create(name="Ringold")
        InstitutionLink.objects.create(institution=institution, type=typo_type, value="123456")
        self.institution_pk = institution.pk

    def test_typo_row_renamed_and_links_follow(self) -> None:
        InstitutionLinkType = self.new_state.apps.get_model("institutions", "InstitutionLinkType")
        InstitutionLink = self.new_state.apps.get_model("institutions", "InstitutionLink")

        assert not InstitutionLinkType.objects.filter(name="Ringold").exists()
        renamed = InstitutionLinkType.objects.get(name="Ringgold")
        link = InstitutionLink.objects.get(institution_id=self.institution_pk)
        assert link.type_id == renamed.pk
        assert link.value == "123456"


@pytest.mark.django_db
class TestMergeRingoldIntoRinggoldLinkType(MigratorTestCase):
    """When both rows exist, links move to the correct row and the typo is dropped."""

    migrate_from = ("institutions", "0008_remove_path_and_node_id")
    migrate_to = ("institutions", "0009_rename_ringold_link_type")

    def prepare(self) -> None:
        Institution = self.old_state.apps.get_model("institutions", "Institution")
        InstitutionLinkType = self.old_state.apps.get_model("institutions", "InstitutionLinkType")
        InstitutionLink = self.old_state.apps.get_model("institutions", "InstitutionLink")

        institution = Institution.objects.create(name="Merged Institution")
        typo_type = InstitutionLinkType.objects.create(name="Ringold")
        correct_type = InstitutionLinkType.objects.create(name="Ringgold")
        InstitutionLink.objects.create(institution=institution, type=typo_type, value="654321")
        InstitutionLink.objects.create(institution=institution, type=correct_type, value="111111")
        ror_type = InstitutionLinkType.objects.create(name="ROR")
        InstitutionLink.objects.create(
            institution=institution, type=ror_type, value="https://ror.org/010nsgg66"
        )
        self.institution_pk = institution.pk
        self.correct_pk = correct_type.pk
        self.ror_pk = ror_type.pk

    def test_typo_row_merged_without_losing_links(self) -> None:
        InstitutionLinkType = self.new_state.apps.get_model("institutions", "InstitutionLinkType")
        InstitutionLink = self.new_state.apps.get_model("institutions", "InstitutionLink")

        assert not InstitutionLinkType.objects.filter(name="Ringold").exists()
        assert InstitutionLinkType.objects.filter(name="Ringgold").count() == 1

        links = list(InstitutionLink.objects.filter(institution_id=self.institution_pk))
        assert {(link.type_id, link.value) for link in links} == {
            (self.correct_pk, "654321"),
            (self.correct_pk, "111111"),
            (self.ror_pk, "https://ror.org/010nsgg66"),
        }

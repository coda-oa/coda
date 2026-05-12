from io import StringIO
from pathlib import Path

import pytest
from django.utils import timezone

from coda.apps.institutions import services
from coda.apps.institutions.models import Institution

ordered_institutions_path = Path(__file__).parent / "test_institutions_ordered.csv"
ordered_institutions_path_with_identifiers = (
    Path(__file__).parent / "test_institutions_with_identifiers.csv"
)
invalid_identifiers_institutions_path = (
    Path(__file__).parent / "test_institutions_with_invalid_identifiers.csv"
)
institutions_with_affiliations_path = (
    Path(__file__).parent / "test_institutions_with_affiliations.csv"
)


@pytest.mark.django_db
def test__can_create_institutions_from_file() -> None:
    with Path(ordered_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    institution_and_parent_names = [
        ("the-root", None),
        ("first-child", "the-root"),
        ("second-child", "the-root"),
        ("first-child-child", "first-child"),
        ("second-child-child", "second-child"),
    ]

    for name, parent_name in institution_and_parent_names:
        assert Institution.objects.filter(name=name, parent__name=parent_name).exists()


@pytest.mark.django_db
def test__uploading_same_list_twice__does_not_duplicate_institutions() -> None:
    with Path(ordered_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    with Path(ordered_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    assert Institution.objects.count() == 5


@pytest.mark.django_db
def test__can_import_institution_with_ror() -> None:
    _imported_institutions_with_identifiers()

    institution = Institution.objects.get(name="the-root")
    assert institution.links.filter(type__name="ROR", value="https://ror.org/010nsgg66").exists()


@pytest.mark.django_db
def test__can_import_institution_with_isni() -> None:
    _imported_institutions_with_identifiers()

    institution = Institution.objects.get(name="first-child")
    normalized_isni_value = "000000012281955X"
    assert institution.links.filter(type__name="ISNI", value=normalized_isni_value).exists()


@pytest.mark.django_db
def test__can_import_institution_with_ringgold() -> None:
    _imported_institutions_with_identifiers()

    institution = Institution.objects.get(name="second-child")
    assert institution.links.filter(type__name="Ringgold", value="123456").exists()


@pytest.mark.django_db
def test__institution_with_invalid_identifiers__is_imported_without_invalid_identifier() -> None:
    with Path(invalid_identifiers_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    institution_invalid_ror = Institution.objects.get(name="institution-with-invalid-ror")
    assert not institution_invalid_ror.links.filter(type__name="ROR").exists()

    institution_invalid_isni = Institution.objects.get(name="institution-with-invalid-isni")
    assert not institution_invalid_isni.links.filter(type__name="ISNI").exists()

    institution_invalid_ringgold = Institution.objects.get(name="institution-with-invalid-ringgold")
    assert not institution_invalid_ringgold.links.filter(type__name="Ringgold").exists()


@pytest.mark.django_db
def test__import_result_contains_errors_for_invalid_identifiers() -> None:
    with Path(invalid_identifiers_institutions_path).open() as file:
        result = services.import_from_file(StringIO(file.read()))

    assert result.total == 3
    assert result.fully_imported == 0
    assert result.partially_imported == 3
    assert len(result.errors) == 3

    error_messages = [error.message for error in result.errors]
    assert any("ROR: Invalid ROR format" in msg for msg in error_messages)
    assert any("ISNI: Invalid ISNI format" in msg for msg in error_messages)
    assert any("Ringgold: Invalid Ringgold format" in msg for msg in error_messages)


@pytest.mark.django_db
def test__institution_with_author_affiliation__is_imported__author_affiliation_is_set_correctly() -> (
    None
):
    with Path(institutions_with_affiliations_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    institution_affiliation_false = Institution.objects.get(
        name="institution-with-affiliation-false"
    )
    assert (
        institution_affiliation_false.virtual is True
    )  # affiliation=false means virtual=True (not usable)

    institution_affiliation_true = Institution.objects.get(name="institution-with-affiliation-true")
    assert (
        institution_affiliation_true.virtual is False
    )  # affiliation=true means virtual=False (usable)

    institution_affiliation_default = Institution.objects.get(
        name="institution-without-affiliation-field"
    )
    assert institution_affiliation_default.virtual is False  # empty defaults to usable


@pytest.mark.django_db
def test__institution_with_identifier_gets_updated_when_name_changes() -> None:
    first_import = StringIO(
        "name;ROR;ISNI;Ringgold\n" + "Biology Department;https://ror.org/010nsgg66;;"
    )
    services.import_from_file(first_import)

    original_institution = Institution.objects.get(name="Biology Department")
    original_pk = original_institution.pk
    assert original_institution.links.filter(
        type__name="ROR", value="https://ror.org/010nsgg66"
    ).exists()

    second_import = StringIO(
        "name;ROR;ISNI;Ringgold\n" + "Department of Biological Sciences;https://ror.org/010nsgg66;;"
    )
    services.import_from_file(second_import)

    assert Institution.objects.count() == 1

    updated_institution = Institution.objects.get(pk=original_pk)
    assert updated_institution.name == "Department of Biological Sciences"
    assert updated_institution.links.filter(
        type__name="ROR", value="https://ror.org/010nsgg66"
    ).exists()


@pytest.mark.django_db
def test__institution_without_identifier_matched_by_name() -> None:
    first_import = StringIO("name;ROR;ISNI;Ringgold\n" + "General Department;;;")
    services.import_from_file(first_import)

    original_institution = Institution.objects.get(name="General Department")
    original_pk = original_institution.pk

    second_import = StringIO("name;ROR;ISNI;Ringgold\n" + "General Department;;;")
    services.import_from_file(second_import)

    assert Institution.objects.count() == 1
    assert Institution.objects.get(pk=original_pk).name == "General Department"


def _imported_institutions_with_identifiers() -> None:
    with Path(ordered_institutions_path_with_identifiers).open() as file:
        services.import_from_file(StringIO(file.read()))


# Internal ID matching tests


@pytest.mark.django_db
def test__institution_with_internal_id__import_with_same_internal_id_but_different_name__matches_by_internal_id_first() -> (
    None
):
    existing = Institution.objects.create(name="Old Name", internal_id="inst_test123")

    csv_data = StringIO("internal_id;name;ROR;ISNI;Ringgold\ninst_test123;New Name;;;")
    services.import_from_file(csv_data)

    assert Institution.objects.count() == 1
    existing.refresh_from_db()
    assert existing.name == "New Name"
    assert existing.internal_id == "inst_test123"


@pytest.mark.django_db
def test__two_institutions_one_with_matching_internal_id_and_one_with_matching_ror__import__prefers_internal_id() -> (
    None
):
    """Given: Two institutions exist - one with matching internal_id, one with matching ROR
    When: CSV import has both internal_id and ROR that match different institutions
    Then: Should prioritize internal_id matching over ROR matching"""
    # Create two institutions: one with internal_id, one with ROR
    inst_with_id = Institution.objects.create(name="Institution A", internal_id="inst_aaa111")
    inst_with_ror = Institution.objects.create(name="Institution B")
    inst_with_ror.links.create(type_id=1, value="https://ror.org/123456")

    csv_data = StringIO(
        "internal_id;name;ROR;ISNI;Ringgold\n" + "inst_aaa111;Updated Name;https://ror.org/123456;;"
    )
    services.import_from_file(csv_data)

    assert Institution.objects.count() == 2
    inst_with_id.refresh_from_db()
    assert inst_with_id.name == "Updated Name"
    assert inst_with_id.internal_id == "inst_aaa111"


@pytest.mark.django_db
def test__institution_with_ror__import_with_no_internal_id_provided__falls_back_to_ror_matching() -> (
    None
):
    existing = Institution.objects.create(name="Test Institution")
    existing.links.create(type_id=1, value="https://ror.org/999888")  # ROR type_id=1

    csv_data = StringIO("name;ROR;ISNI;Ringgold\nUpdated Name;https://ror.org/999888;;")
    services.import_from_file(csv_data)

    assert Institution.objects.count() == 1
    existing.refresh_from_db()
    assert existing.name == "Updated Name"


@pytest.mark.django_db
def test__parent_institution_with_internal_id_in_csv__import_child_institution_with_parent_internal_id__links_parent_correctly() -> (
    None
):
    parent = Institution.objects.create(name="Parent Institution", internal_id="inst_parent1")

    csv_data = StringIO(
        "internal_id;name;parent;ROR;ISNI;Ringgold\ninst_child1;Child Institution;inst_parent1;;;"
    )
    services.import_from_file(csv_data)

    child = Institution.objects.get(internal_id="inst_child1")
    assert child.parent == parent
    assert child.parent.internal_id == "inst_parent1"


@pytest.mark.django_db
def test__csv_with_full_institution_hierarchy__import__creates_proper_tree() -> None:
    csv_data = StringIO(
        "internal_id;name;parent;ROR;ISNI;Ringgold\n"
        "inst_root;Root Institution;;;;\n"
        "inst_child1;Child 1;inst_root;;;\n"
        "inst_child2;Child 2;inst_root;;;\n"
        "inst_grandchild;Grandchild;inst_child1;;;"
    )

    services.import_from_file(csv_data)

    root = Institution.objects.get(internal_id="inst_root")
    child1 = Institution.objects.get(internal_id="inst_child1")
    child2 = Institution.objects.get(internal_id="inst_child2")
    grandchild = Institution.objects.get(internal_id="inst_grandchild")

    assert root.parent is None
    assert child1.parent == root
    assert child2.parent == root
    assert grandchild.parent == child1


@pytest.mark.django_db
def test__csv_with_archived_institutions__import__sets_archived_at() -> None:
    """Given: CSV contains archived=true
    When: Institution is imported
    Then: Institution should be archived (archived_at set)"""
    csv_data = StringIO(
        "internal_id;name;archived;ROR;ISNI;Ringgold\n" + "inst_arch1;Archived Institution;true;;;"
    )
    services.import_from_file(csv_data)

    inst = Institution.all_objects.get(internal_id="inst_arch1")
    assert inst.archived_at is not None


@pytest.mark.django_db
def test__archived_institution_in_db__import_setting_archived_false_in_csv__clears_archived_at() -> (
    None
):
    inst = Institution.objects.create(
        name="Previously Archived", internal_id="inst_prev1", archived_at=timezone.now()
    )

    csv_data = StringIO(
        "internal_id;name;archived;ROR;ISNI;Ringgold\n" + "inst_prev1;Previously Archived;false;;;"
    )
    services.import_from_file(csv_data)

    inst.refresh_from_db()
    assert inst.archived_at is None


@pytest.mark.django_db
def test__csv_with_archived_column_absent__import__leaves_status_unchanged() -> None:
    archived_inst = Institution.objects.create(
        name="Archived", internal_id="inst_keep_arch", archived_at=timezone.now()
    )
    archived_time = archived_inst.archived_at
    active_inst = Institution.objects.create(name="Active", internal_id="inst_keep_active")

    csv_data = StringIO(
        "internal_id;name;ROR;ISNI;Ringgold\n"
        "inst_keep_arch;Archived Updated;;;\n"
        "inst_keep_active;Active Updated;;;"
    )
    services.import_from_file(csv_data)

    archived_inst.refresh_from_db()
    assert archived_inst.archived_at == archived_time
    active_inst.refresh_from_db()
    assert active_inst.archived_at is None


@pytest.mark.django_db
def test__institution_with_matching_internal_id_and_changed_ror__import__updates_ror() -> None:
    inst = Institution.objects.create(name="Test University", internal_id="inst_typo1")
    inst.links.create(type_id=1, value="https://ror.org/02mhbdp94")  # Old ROR

    csv_data = StringIO(
        "internal_id;name;ROR;ISNI;Ringgold\ninst_typo1;Test University;https://ror.org/010nsgg66;;"
    )
    services.import_from_file(csv_data)

    inst.refresh_from_db()
    assert inst.links.filter(type__name="ROR", value="https://ror.org/010nsgg66").exists()
    assert not inst.links.filter(type__name="ROR", value="https://ror.org/02mhbdp94").exists()


@pytest.mark.django_db
def test__institution_with_matching_internal_id_and_empty_ror__import__preserves_existing_ror() -> (
    None
):
    inst = Institution.objects.create(name="Test University", internal_id="inst_keep1")
    inst.links.create(type_id=1, value="https://ror.org/010nsgg66")

    csv_data = StringIO(
        "internal_id;name;ROR;ISNI;Ringgold\n" + "inst_keep1;Test University Updated;;;"
    )
    services.import_from_file(csv_data)

    inst.refresh_from_db()
    assert inst.links.filter(type__name="ROR", value="https://ror.org/010nsgg66").exists()


@pytest.mark.django_db
def test__institution_with_matching_internal_id_and_updated_identifiers__import__updates_all_identifiers() -> (
    None
):
    inst = Institution.objects.create(name="Test University", internal_id="inst_multi1")
    inst.links.create(type_id=1, value="https://ror.org/02mhbdp94")
    inst.links.create(type_id=2, value="0000000121032683")
    inst.links.create(type_id=3, value="111111")

    csv_data = StringIO(
        "internal_id;name;ROR;ISNI;Ringgold\n"
        "inst_multi1;Test University;https://ror.org/010nsgg66;000000012281955X;123456"
    )
    services.import_from_file(csv_data)

    inst.refresh_from_db()
    assert inst.links.filter(type__name="ROR", value="https://ror.org/010nsgg66").exists()
    assert not inst.links.filter(type__name="ROR", value="https://ror.org/02mhbdp94").exists()

    assert inst.links.filter(type__name="ISNI", value="000000012281955X").exists()
    assert not inst.links.filter(type__name="ISNI", value="0000000121032683").exists()

    assert inst.links.filter(type__name="Ringgold", value="123456").exists()
    assert not inst.links.filter(type__name="Ringgold", value="111111").exists()


@pytest.mark.django_db
def test__parent_institution_archived_but_child_not_archived__import__produces_error() -> None:
    """Given: CSV tries to archive parent but not child
    When: Import is attempted
    Then: Parent is not archived and error is reported"""
    csv_data = StringIO(
        "internal_id;name;parent;archived;ROR;ISNI;Ringgold\n"
        "inst_parent1;Parent Institution;;true;;;\n"
        "inst_child1;Child Institution;inst_parent1;false;;;"
    )
    result = services.import_from_file(csv_data)

    parent = Institution.all_objects.get(internal_id="inst_parent1")
    child = Institution.all_objects.get(internal_id="inst_child1")

    # Parent should NOT be archived because child is not archived
    assert parent.archived_at is None
    assert child.archived_at is None

    # Error should be reported
    assert len(result.errors) == 1
    assert "Parent Institution" in result.errors[0].institution_name
    assert "unarchived descendant" in result.errors[0].message.lower()


@pytest.mark.django_db
def test__parent_and_child_both_archived__import__succeeds() -> None:
    """Given: CSV archives both parent and child
    When: Import is attempted
    Then: Both are archived successfully"""
    csv_data = StringIO(
        "internal_id;name;parent;archived;ROR;ISNI;Ringgold\n"
        "inst_parent2;Parent Institution;;true;;;\n"
        "inst_child2;Child Institution;inst_parent2;true;;;"
    )
    result = services.import_from_file(csv_data)

    parent = Institution.all_objects.get(internal_id="inst_parent2")
    child = Institution.all_objects.get(internal_id="inst_child2")

    # Both should be archived
    assert parent.archived_at is not None
    assert child.archived_at is not None

    # Both should be marked as virtual
    assert parent.virtual is True
    assert child.virtual is True

    # No errors
    assert len(result.errors) == 0


@pytest.mark.django_db
def test__csv_with_cyclic_parent_relationship__import__produces_error() -> None:
    """Given: An existing institution is given a parent that is one of its own descendants
    When: Import is attempted
    Then: An error is reported for the institution with the cyclic parent"""
    parent = Institution.objects.create(name="Parent Institution", internal_id="inst_cycle_parent")
    _ = Institution.objects.create(
        name="Child Institution", internal_id="inst_cycle_child", parent=parent
    )

    # Try to make the parent a child of its own child (cycle)
    csv_data = StringIO(
        "internal_id;name;parent;ROR;ISNI;Ringgold\n"
        "inst_cycle_parent;Parent Institution;inst_cycle_child;;;"
    )
    result = services.import_from_file(csv_data)

    assert len(result.errors) == 1
    assert "Parent Institution" in result.errors[0].institution_name
    assert "cycle" in result.errors[0].message.lower()


@pytest.mark.django_db
def test__csv_with_cyclic_parent_relationship__import__institution_is_imported_without_parent() -> (
    None
):
    """Given: An existing institution is given a parent that is one of its own descendants
    When: Import is attempted
    Then: The institution is still imported but its parent is left unchanged"""
    parent = Institution.objects.create(name="Parent Institution", internal_id="inst_cycle2_parent")
    child = Institution.objects.create(
        name="Child Institution", internal_id="inst_cycle2_child", parent=parent
    )

    csv_data = StringIO(
        "internal_id;name;parent;ROR;ISNI;Ringgold\n"
        "inst_cycle2_parent;Parent Institution;inst_cycle2_child;;;"
    )
    services.import_from_file(csv_data)

    parent.refresh_from_db()
    assert parent.parent != child


@pytest.mark.django_db
def test__active_child_on_third_level__cannot_archive_root__import__produces_error() -> None:
    """Given: CSV tries to archive root and child but has active grandchild at third level
    When: Import is attempted
    Then: Neither root nor child are archived and errors are reported"""
    csv_data = StringIO(
        "internal_id;name;parent;archived;ROR;ISNI;Ringgold\n"
        "inst_root;Root Institution;;true;;;\n"
        "inst_child1;Child 1;inst_root;true;;;\n"
        "inst_grandchild1;Grandchild 1;inst_child1;false;;;"
    )
    result = services.import_from_file(csv_data)

    root = Institution.all_objects.get(internal_id="inst_root")
    child1 = Institution.all_objects.get(internal_id="inst_child1")
    grandchild1 = Institution.all_objects.get(internal_id="inst_grandchild1")

    # Root should NOT be archived because grandchild is not archived
    assert root.archived_at is None
    # Child1 should also NOT be archived because its child (grandchild) is not archived
    assert child1.archived_at is None
    assert grandchild1.archived_at is None

    # Errors should be reported for both root and child1
    assert len(result.errors) == 2
    error_messages = [error.institution_name for error in result.errors]
    assert "Root Institution" in error_messages
    assert "Child 1" in error_messages
    # All errors should mention unarchived descendants
    for error in result.errors:
        assert "unarchived descendant" in error.message.lower()

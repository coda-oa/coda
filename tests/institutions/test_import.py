from io import StringIO
from pathlib import Path

import pytest

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
def test__can_create_institutions_with_identifiers() -> None:
    with Path(ordered_institutions_path_with_identifiers).open() as file:
        services.import_from_file(StringIO(file.read()))

    institution_and_identifiers = [
        ("the-root", None, "https://ror.org/010nsgg66", None, None),
        ("first-child", "the-root", None, "0000 0001 2281 955X", None),
        ("second-child", "the-root", None, None, "123456"),
        ("first-child-child", "first-child", None, None, None),
        ("second-child-child", "second-child", None, None, None),
    ]

    for name, parent_name, ror_value, isni_value, ringgold_value in institution_and_identifiers:
        institution = Institution.objects.get(name=name)
        if parent_name:
            assert institution.parent is not None
            assert institution.parent.name == parent_name
        else:
            assert institution.parent is None

        if ror_value:
            assert institution.links.filter(type__name="ROR", value=ror_value).exists()
        if isni_value:
            normalized_isni_value = isni_value.replace(" ", "").replace("-", "").upper()
            assert institution.links.filter(type__name="ISNI", value=normalized_isni_value).exists()
        if ringgold_value:
            assert institution.links.filter(type__name="Ringgold", value=ringgold_value).exists()


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
        "name;ROR;ISNI;Ringgold\nBiology Department;https://ror.org/010nsgg66;;"
    )
    services.import_from_file(first_import)

    original_institution = Institution.objects.get(name="Biology Department")
    original_pk = original_institution.pk
    assert original_institution.links.filter(
        type__name="ROR", value="https://ror.org/010nsgg66"
    ).exists()

    second_import = StringIO(
        "name;ROR;ISNI;Ringgold\nDepartment of Biological Sciences;https://ror.org/010nsgg66;;"
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
    first_import = StringIO("name;ROR;ISNI;Ringgold\nGeneral Department;;;")
    services.import_from_file(first_import)

    original_institution = Institution.objects.get(name="General Department")
    original_pk = original_institution.pk

    second_import = StringIO("name;ROR;ISNI;Ringgold\nGeneral Department;;;")
    services.import_from_file(second_import)

    assert Institution.objects.count() == 1
    assert Institution.objects.get(pk=original_pk).name == "General Department"

from django.test import Client
import pytest
import polars as pl
from io import StringIO
from django.utils import timezone
from django.urls import reverse

from coda.apps.institutions.models import Institution
from coda.apps.institutions.services import export_to_csv
from coda.apps.institutions import services


@pytest.mark.django_db
def test__export__active_and_archived_exist__both_included_in_csv() -> None:
    Institution.objects.create(name="Active", internal_id="inst_act1")
    Institution.objects.create(name="Archived", internal_id="inst_arc1", archived_at=timezone.now())

    csv_content = export_to_csv()
    df = pl.read_csv(StringIO(csv_content), separator=";")

    assert len(df) == 2
    assert "inst_act1" in df["internal_id"].to_list()
    assert "inst_arc1" in df["internal_id"].to_list()


@pytest.mark.django_db
def test__export__csv_generated__contains_all_required_columns() -> None:
    Institution.objects.create(name="Test", internal_id="inst_test1")

    csv_content = export_to_csv()
    df = pl.read_csv(StringIO(csv_content), separator=";")

    expected_columns = [
        "internal_id",
        "name",
        "parent",
        "usableAffiliation",
        "archived",
        "ROR",
        "ISNI",
        "Ringgold",
    ]
    assert df.columns == expected_columns


@pytest.mark.django_db
def test__export__parent_child_exists__parent_column_contains_internal_id() -> None:
    parent = Institution.objects.create(name="Parent", internal_id="inst_par1")
    _ = Institution.objects.create(name="Child", internal_id="inst_chi1", parent=parent)

    csv_content = export_to_csv()
    df = pl.read_csv(StringIO(csv_content), separator=";")

    child_row = df.filter(pl.col("internal_id") == "inst_chi1")
    assert child_row["parent"][0] == "inst_par1"

    parent_row = df.filter(pl.col("internal_id") == "inst_par1")
    parent_value = parent_row["parent"][0]
    # Parent has no parent - should be empty
    assert parent_value in [None, ""] or str(parent_value) == "nan"


@pytest.mark.django_db
def test__export__virtual_flag_set__usable_affiliation_inverted() -> None:
    Institution.objects.create(name="Virtual", internal_id="inst_vir1", virtual=True)
    Institution.objects.create(name="Real", internal_id="inst_rea1", virtual=False)

    csv_content = export_to_csv()
    df = pl.read_csv(StringIO(csv_content), separator=";")

    virtual_row = df.filter(pl.col("internal_id") == "inst_vir1")
    assert str(virtual_row["usableAffiliation"][0]).lower() == "false"

    real_row = df.filter(pl.col("internal_id") == "inst_rea1")
    assert str(real_row["usableAffiliation"][0]).lower() == "true"


@pytest.mark.django_db
def test__export__institution_without_id__internal_id_generated() -> None:
    inst = Institution.objects.create(name="No ID", internal_id="")

    _ = export_to_csv()

    inst.refresh_from_db()
    assert inst.internal_id is not None
    assert inst.internal_id.startswith("inst_")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export_view__requested__returns_csv_download(client: Client) -> None:
    Institution.objects.create(name="Test Institution", internal_id="inst_test1")

    url = reverse("institutions:export")
    response = client.get(url)

    assert response["Content-Type"] == "text/csv"
    assert "attachment; filename=" in response["Content-Disposition"]
    assert "institutions" in response["Content-Disposition"]

    content = response.content.decode("utf-8")
    assert "internal_id" in content
    assert "inst_test1" in content


@pytest.mark.django_db
def test__institutions_exist__export_and_reimport_with_name_change__updates_without_duplicating() -> (
    None
):
    inst = Institution.objects.create(name="Old Name University", internal_id="inst_001")

    csv_export = services.export_to_csv()
    modified_csv = csv_export.replace("Old Name University", "New Name University")

    services.import_from_file(StringIO(modified_csv))

    assert Institution.objects.count() == 1
    inst.refresh_from_db()
    assert inst.name == "New Name University"
    assert inst.internal_id == "inst_001"  # ID unchanged


@pytest.mark.django_db
@pytest.mark.parametrize(
    "identifier_type,type_id,old_value,new_value",
    [
        ("ROR", 1, "https://ror.org/02mhbdp94", "https://ror.org/010nsgg66"),
        ("ISNI", 2, "0000000121032683", "000000012281955X"),
        ("Ringgold", 3, "999999", "123456"),
    ],
)
def test__institutions_exist__export_and_reimport_with_identifier_change__updates_identifier(
    identifier_type: str, type_id: int, old_value: str, new_value: str
) -> None:
    inst = Institution.objects.create(name="Test University", internal_id="inst_002")
    inst.links.create(type_id=type_id, value=old_value)

    csv_export = services.export_to_csv()
    modified_csv = csv_export.replace(old_value, new_value)
    services.import_from_file(StringIO(modified_csv))

    inst.refresh_from_db()
    assert inst.links.filter(type__name=identifier_type, value=new_value).exists()
    assert not inst.links.filter(type__name=identifier_type, value=old_value).exists()


@pytest.mark.django_db
def test__institutions_exist__export_and_reimport_with_affiliation_change__updates_virtual_flag() -> (
    None
):
    inst = Institution.objects.create(
        name="Test Institution", internal_id="inst_003", virtual=True  # Not usable for affiliations
    )

    csv_export = services.export_to_csv()
    lines = csv_export.split("\n")
    for i, line in enumerate(lines):
        if "inst_003" in line:
            parts = line.split(";")
            parts[3] = "true"  # usableAffiliation column
            lines[i] = ";".join(parts)
    modified_csv = "\n".join(lines)
    services.import_from_file(StringIO(modified_csv))

    inst.refresh_from_db()
    assert inst.virtual is False


@pytest.mark.django_db
def test__multiple_institutions_exist__export_and_reimport_preserves_unchanged_institutions() -> (
    None
):
    inst1 = Institution.objects.create(name="Institution 1", internal_id="inst_004")
    inst2 = Institution.objects.create(name="Institution 2", internal_id="inst_005")

    csv_export = services.export_to_csv()
    modified_csv = csv_export.replace("Institution 1", "Institution One")
    services.import_from_file(StringIO(modified_csv))

    inst1.refresh_from_db()
    inst2.refresh_from_db()
    assert inst1.name == "Institution One"
    assert inst2.name == "Institution 2"

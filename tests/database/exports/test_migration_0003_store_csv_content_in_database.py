import pytest
from django.core.files.base import ContentFile
from django_test_migrations.contrib.unittest_case import MigratorTestCase

CSV_HEADER = "request_id;publication_title\n"
CSV_BODY = "REQ-1;Stored Publication\n"


@pytest.mark.django_db
class TestStoreCSVContentForward(MigratorTestCase):
    """Forward migration 0002 -> 0003: every stored CSV file becomes row content."""

    migrate_from = ("exports", "0002_fundingrequestcsvexport_csv_file")
    migrate_to = ("exports", "0003_store_csv_content_in_database")

    def prepare(self) -> None:
        Export = self.old_state.apps.get_model("exports", "FundingRequestCSVExport")

        with_file = Export.objects.create(
            name="Existing export",
            filters={"period_start": "2024-01-01", "period_end": "2024-12-31"},
            record_count=1,
            csv_file=ContentFile(f"\ufeff{CSV_HEADER}{CSV_BODY}", name="existing.csv"),
        )
        self.with_file_pk = with_file.pk

        without_file = Export.objects.create(
            name="Export without file",
            filters={"period_start": "2024-01-01", "period_end": "2024-12-31"},
            record_count=2,
        )
        self.without_file_pk = without_file.pk

        missing_file = Export.objects.create(
            name="Export with missing file",
            filters={"period_start": "2024-01-01", "period_end": "2024-12-31"},
            record_count=3,
            csv_file=ContentFile(f"\ufeff{CSV_HEADER}{CSV_BODY}", name="missing.csv"),
        )
        missing_file.csv_file.storage.delete(missing_file.csv_file.name)
        self.missing_file_pk = missing_file.pk

    def test_file_content_is_stored_without_bom(self) -> None:
        Export = self.new_state.apps.get_model("exports", "FundingRequestCSVExport")
        export = Export.objects.get(pk=self.with_file_pk)

        assert export.csv_content == f"{CSV_HEADER}{CSV_BODY}"
        assert export.record_count == 1
        assert export.filters == {"period_start": "2024-01-01", "period_end": "2024-12-31"}

    def test_export_without_file_keeps_empty_content(self) -> None:
        Export = self.new_state.apps.get_model("exports", "FundingRequestCSVExport")
        export = Export.objects.get(pk=self.without_file_pk)

        assert export.csv_content == ""
        assert export.record_count == 2

    def test_missing_file_does_not_abort_migration(self) -> None:
        Export = self.new_state.apps.get_model("exports", "FundingRequestCSVExport")
        export = Export.objects.get(pk=self.missing_file_pk)

        assert export.csv_content == ""
        assert export.record_count == 3

    def test_file_field_is_removed(self) -> None:
        Export = self.new_state.apps.get_model("exports", "FundingRequestCSVExport")
        field_names = {field.name for field in Export._meta.get_fields()}

        assert "csv_content" in field_names
        assert "csv_file" not in field_names


@pytest.mark.django_db
class TestStoreCSVContentReverse(MigratorTestCase):
    """Reverse migration 0003 -> 0002: the schema is restored, the rows survive."""

    migrate_from = ("exports", "0003_store_csv_content_in_database")
    migrate_to = ("exports", "0002_fundingrequestcsvexport_csv_file")

    def prepare(self) -> None:
        Export = self.old_state.apps.get_model("exports", "FundingRequestCSVExport")
        export = Export.objects.create(
            name="Generated export",
            filters={"period_start": "2024-01-01", "period_end": "2024-12-31"},
            record_count=1,
            csv_content=f"{CSV_HEADER}{CSV_BODY}",
        )
        self.export_pk = export.pk

    def test_row_survives_with_restored_file_field(self) -> None:
        Export = self.new_state.apps.get_model("exports", "FundingRequestCSVExport")
        export = Export.objects.get(pk=self.export_pk)
        field_names = {field.name for field in Export._meta.get_fields()}

        assert "csv_file" in field_names
        assert "csv_content" not in field_names
        assert not export.csv_file
        assert export.record_count == 1

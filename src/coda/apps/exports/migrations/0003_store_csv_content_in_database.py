from django.db import migrations, models


def store_csv_content(apps, schema_editor):
    """Copy every stored CSV file into its export row, then let the file field go.

    A missing or undecodable file leaves ``csv_content`` empty instead of aborting the
    migration: the export keeps its metadata and can be regenerated from its filters.
    The reverse is a no-op, so rolling back means restoring the database backup taken
    before this migration; the old files stay on disk until they are cleaned up.
    """

    Export = apps.get_model("exports", "FundingRequestCSVExport")

    for export in Export.objects.exclude(csv_file__isnull=True).exclude(csv_file="").iterator():
        try:
            with export.csv_file.open("rb") as file:
                export.csv_content = file.read().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        export.save(update_fields=["csv_content"])


class Migration(migrations.Migration):
    dependencies = [
        ("exports", "0002_fundingrequestcsvexport_csv_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="fundingrequestcsvexport",
            name="csv_content",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Generated CSV snapshot; empty string means the artifact is unavailable",
            ),
        ),
        migrations.RunPython(store_csv_content, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="fundingrequestcsvexport",
            name="csv_file",
        ),
    ]

from django.db import migrations

from . import _backfill_opencost_v1


class Migration(migrations.Migration):
    """Store a document for every report generated before xml_content existed.

    The transform runs from the report's snapshot tree, the record of what was generated,
    through the frozen copy of that era's transform in ``_backfill_opencost_v1`` - migrations
    must replay identically forever, so this one owns its own transform instead of importing
    the application's. The reverse is a no-op: undoing it would blank documents that were
    never absent, and the rows a down-migration returns to still stand as they were.
    """

    dependencies = [
        ("contracts", "0004_add_contract_links"),
        ("fundingrequests", "0037_add_archived_at_to_fundingorganization"),
        ("opencost", "0013_add_opencost_seed_outcome_columns"),
        ("publications", "0047_merge_20260112_0843"),
    ]

    operations = [
        migrations.RunPython(
            _backfill_opencost_v1.backfill_reports,
            migrations.RunPython.noop,
        ),
    ]

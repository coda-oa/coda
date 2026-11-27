"""Defensive fix for the "Ringold" typo in manually created link types.

The canonical spelling of the identifier is "Ringgold"; the fixtures and all
application code use it. The openCost *wire* vocabulary carried the typo
("ringold", spec §4.1.1 up to opencost 0.2), which could leak into
``InstitutionLinkType`` names. Rename any such row; if a correctly spelled
row already exists, move the links over and drop the typo row instead.
"""

from django.db import migrations


def rename_ringold_to_ringgold(apps, schema_editor):
    InstitutionLinkType = apps.get_model("institutions", "InstitutionLinkType")
    InstitutionLink = apps.get_model("institutions", "InstitutionLink")

    typo = InstitutionLinkType.objects.filter(name="Ringold").first()
    if typo is None:
        return

    correct = InstitutionLinkType.objects.filter(name="Ringgold").first()
    if correct is None:
        typo.name = "Ringgold"
        typo.save(update_fields=["name"])
        return

    InstitutionLink.objects.filter(type=typo).update(type=correct)
    typo.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("institutions", "0008_remove_path_and_node_id"),
    ]

    operations = [
        # Reverse is a no-op: the forward pass is a data cleanup that may merge
        # two rows, which cannot be faithfully un-merged, and blindly renaming
        # "Ringgold" back would also corrupt fixture-provided rows.
        migrations.RunPython(rename_ringold_to_ringgold, migrations.RunPython.noop),
    ]

from django.db import migrations


def lowercase_ror_link_values(apps, schema_editor):
    InstitutionLink = apps.get_model("institutions", "InstitutionLink")
    for link in InstitutionLink.objects.filter(type__name="ROR").iterator():
        lowered = link.value.lower()
        if lowered != link.value:
            link.value = lowered
            link.save(update_fields=["value"])


def _no_reverse(_apps, _schema_editor):
    """Original letter case of ROR identifiers is not restored."""


class Migration(migrations.Migration):
    dependencies = [
        ("institutions", "0010_alter_institutionlinktype_options"),
    ]

    operations = [
        migrations.RunPython(lowercase_ror_link_values, _no_reverse),
    ]

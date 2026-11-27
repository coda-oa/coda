from django.db import migrations


def lowercase_ror_link_values(apps, schema_editor):
    FundingOrganizationLink = apps.get_model("fundingrequests", "FundingOrganizationLink")
    for link in FundingOrganizationLink.objects.filter(type__name="ROR").iterator():
        lowered = link.value.lower()
        if lowered != link.value:
            link.value = lowered
            link.save(update_fields=["value"])


def _no_reverse(_apps, _schema_editor):
    """Original letter case of ROR identifiers is not restored."""


class Migration(migrations.Migration):
    dependencies = [
        ("fundingrequests", "0038_collapse_duplicate_labels"),
    ]

    operations = [
        migrations.RunPython(lowercase_ror_link_values, _no_reverse),
    ]

from django.db import migrations


def seed_crossref_link_type(apps, schema_editor):
    FundingOrganizationLinkType = apps.get_model("fundingrequests", "FundingOrganizationLinkType")
    FundingOrganizationLinkType.objects.get_or_create(name="Crossref")


class Migration(migrations.Migration):

    dependencies = [
        ("fundingrequests", "0035_seed_link_types"),
    ]

    operations = [
        migrations.RunPython(seed_crossref_link_type, migrations.RunPython.noop),
    ]

from django.db import migrations


def seed_link_types(apps, schema_editor):
    FundingOrganizationLinkType = apps.get_model("fundingrequests", "FundingOrganizationLinkType")
    FundingOrganizationLinkType.objects.bulk_create(
        [FundingOrganizationLinkType(name="DOI"), FundingOrganizationLinkType(name="ROR")]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("fundingrequests", "0034_fundingorganizationlinktype_fundingorganizationlink"),
    ]

    operations = [
        migrations.RunPython(seed_link_types, migrations.RunPython.noop),
    ]

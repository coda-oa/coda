from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("preferences", "0012_alter_globalpreferences_home_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalpreferences",
            name="crossref_contact_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Email address Crossref can contact about our requests",
            ),
        ),
        migrations.AddField(
            model_name="globalpreferences",
            name="crossref_plus_api_token",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Key for faster Crossref access",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="globalpreferences",
            name="crossref_plus_api_token_valid",
            field=models.BooleanField(
                default=None,
                help_text=(
                    "None: no verdict (no key saved or never checked). "
                    "True: Crossref confirmed the key. False: Crossref rejected it "
                    "(e.g. expired); requests then go out without it until a new key "
                    "is saved or a status check confirms it"
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="globalpreferences",
            name="home_institution",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                to="institutions.institution",
            ),
        ),
    ]

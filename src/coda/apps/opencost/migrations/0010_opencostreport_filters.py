from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opencost", "0009_opencostreport_errors_count_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="opencostreport",
            name="filters",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

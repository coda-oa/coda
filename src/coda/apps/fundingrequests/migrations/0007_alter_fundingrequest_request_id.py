# Generated by Django 4.2.8 on 2024-02-26 16:25

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fundingrequests", "0006_alter_fundingrequest_request_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fundingrequest",
            name="request_id",
            field=models.CharField(default="coda-f006c41d-2024-02-26", max_length=25, unique=True),
        ),
    ]
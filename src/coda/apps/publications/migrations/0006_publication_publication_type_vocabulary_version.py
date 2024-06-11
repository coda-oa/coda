# Generated by Django 4.2.8 on 2024-06-11 06:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0005_vocabulary_concept"),
    ]

    operations = [
        migrations.AddField(
            model_name="publication",
            name="publication_type",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="publications",
                to="publications.concept",
            ),
        ),
        migrations.AddField(
            model_name="vocabulary",
            name="version",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]

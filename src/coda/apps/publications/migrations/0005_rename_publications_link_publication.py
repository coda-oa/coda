# Generated by Django 4.2.8 on 2024-02-27 15:16

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0004_alter_link_publications"),
    ]

    operations = [
        migrations.RenameField(
            model_name="link",
            old_name="publications",
            new_name="publication",
        ),
    ]
# Generated by Django 4.2.8 on 2024-02-26 16:25

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("authors", "0005_remove_person_email_remove_person_name_author_email_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="author",
            old_name="details",
            new_name="identifier",
        ),
    ]

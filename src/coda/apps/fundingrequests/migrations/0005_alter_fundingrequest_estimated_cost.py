# Generated by Django 4.2.8 on 2024-05-14 14:06

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fundingrequests", "0004_alter_fundingrequest_payment_method_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fundingrequest",
            name="estimated_cost",
            field=models.DecimalField(decimal_places=4, max_digits=10),
        ),
    ]
# Generated by Django 4.2.8 on 2024-07-02 10:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0009_creditor_alter_invoice_creditor"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="status",
            field=models.CharField(default="unpaid", max_length=255),
        ),
    ]

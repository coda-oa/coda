# Generated by Django 4.2.8 on 2024-06-03 07:19

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0002_remove_invoice_positions_invoice_number_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="invoice",
            old_name="recipient",
            new_name="creditor",
        ),
    ]
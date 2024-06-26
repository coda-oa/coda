# Generated by Django 4.2.8 on 2024-05-13 08:14

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fundingrequests", "0003_alter_fundingrequest_payment_method_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fundingrequest",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("direct", "Direct"),
                    ("reimbursement", "Reimbursement"),
                    ("unknown", "Unknown"),
                ],
                default="unknown",
            ),
        ),
        migrations.AlterField(
            model_name="fundingrequest",
            name="processing_status",
            field=models.CharField(
                choices=[
                    ("approved", "Approved"),
                    ("open", "In Progress"),
                    ("rejected", "Rejected"),
                ],
                default="open",
                max_length=20,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0031_unique_name_among_budgets"),
    ]

    operations = [
        migrations.AlterField(
            model_name="budgettransfer",
            name="source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="transfers_out",
                to="invoices.fundingsource",
            ),
        ),
    ]

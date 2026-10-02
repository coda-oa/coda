from django.db import migrations


class Migration(migrations.Migration):
    """Drop the snapshot schema: the seven child tables and the copied columns.

    The stored document is the record of a report's content: identifiers, links, positions
    and every copied display value are either read back from that document or re-derived
    from CODA on regeneration, so the membership rows keep only what neither source
    states. The backfill migration before this one turned every legacy snapshot tree into
    such a document, which is what makes the tables droppable in the first place.

    Down-migrating recreates the schema but not its content - the child tables come back
    empty - so a rollback past this point is only real as a database restore.
    """

    dependencies = [
        ("opencost", "0014_backfill_opencost_xml"),
    ]

    operations = [
        migrations.DeleteModel(
            name="OpenCostReportContractInstitutionIdentifier",
        ),
        migrations.DeleteModel(
            name="OpenCostReportContractInvoicePosition",
        ),
        migrations.DeleteModel(
            name="OpenCostReportContractSecondaryIdentifier",
        ),
        migrations.DeleteModel(
            name="OpenCostReportInstitutionIdentifier",
        ),
        migrations.DeleteModel(
            name="OpenCostReportInvoicePosition",
        ),
        migrations.DeleteModel(
            name="OpenCostReportPublicationContract",
        ),
        migrations.DeleteModel(
            name="OpenCostReportPublicationLink",
        ),
        migrations.RemoveField(
            model_name="opencostreport",
            name="errors_count",
        ),
        migrations.RemoveField(
            model_name="opencostreport",
            name="warnings_count",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontract",
            name="contract_name",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontract",
            name="institution_name",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontract",
            name="participation_from",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontract",
            name="participation_to",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontract",
            name="primary_identifier_value",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontract",
            name="snapshot_date",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="amount_invoice",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="amount_invoice_currency",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="creditor",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="group_id",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="invoice_date",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="invoice_number",
        ),
        migrations.RemoveField(
            model_name="opencostreportcontractinvoice",
            name="snapshot_date",
        ),
        migrations.RemoveField(
            model_name="opencostreportinvoice",
            name="creditor",
        ),
        migrations.RemoveField(
            model_name="opencostreportinvoice",
            name="invoice_date",
        ),
        migrations.RemoveField(
            model_name="opencostreportinvoice",
            name="invoice_number",
        ),
        migrations.RemoveField(
            model_name="opencostreportinvoice",
            name="snapshot_date",
        ),
        migrations.RemoveField(
            model_name="opencostreportpublication",
            name="doi",
        ),
        migrations.RemoveField(
            model_name="opencostreportpublication",
            name="external_costsplitting",
        ),
        migrations.RemoveField(
            model_name="opencostreportpublication",
            name="institution_name",
        ),
        migrations.RemoveField(
            model_name="opencostreportpublication",
            name="journal",
        ),
        migrations.RemoveField(
            model_name="opencostreportpublication",
            name="publication_type",
        ),
        migrations.RemoveField(
            model_name="opencostreportpublication",
            name="snapshot_date",
        ),
    ]

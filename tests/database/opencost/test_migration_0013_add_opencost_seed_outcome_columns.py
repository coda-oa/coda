import datetime
from typing import Any

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase

SEED_MODELS = (
    "OpenCostReportPublication",
    "OpenCostReportInvoice",
    "OpenCostReportContract",
    "OpenCostReportContractInvoice",
)


def create_publication(apps: Any, title: str) -> Any:
    """Create a publication in a historical app state.

    ``subject_area``/``publication_type`` carry callable defaults that write through
    the CURRENT models (whose schema can be ahead of the migrated-to state), so they
    are always supplied explicitly here.
    """
    Vocabulary = apps.get_model("publications", "Vocabulary")
    AttachedConcept = apps.get_model("publications", "PublicationAttachedConcept")
    Publication = apps.get_model("publications", "Publication")

    vocab = Vocabulary.objects.create(name=f"{title} vocabulary")
    return Publication.objects.create(
        title=title,
        subject_area=AttachedConcept.objects.create(vocabulary=vocab, name="legacy"),
        publication_type=AttachedConcept.objects.create(vocabulary=vocab, name="legacy"),
    )


@pytest.mark.django_db
class TestSeedOutcomeColumnsForward(MigratorTestCase):
    """Forward migration 0012 -> 0013: the four seed tables gain the exported/
    had_errors/ordinal columns and switch their default ordering to id."""

    migrate_from = ("opencost", "0012_add_opencostreport_xml_content_and_issues")
    migrate_to = ("opencost", "0013_add_opencost_seed_outcome_columns")

    def prepare(self) -> None:
        """Create legacy snapshot rows before the outcome columns exist."""
        apps = self.old_state.apps

        Report = apps.get_model("opencost", "OpenCostReport")
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")
        ReportInvoice = apps.get_model("opencost", "OpenCostReportInvoice")
        ReportContract = apps.get_model("opencost", "OpenCostReportContract")
        ReportContractInvoice = apps.get_model("opencost", "OpenCostReportContractInvoice")
        Contract = apps.get_model("contracts", "Contract")
        Invoice = apps.get_model("invoices", "Invoice")
        Creditor = apps.get_model("invoices", "Creditor")

        report = Report.objects.create(
            title="Legacy report",
            period_start=datetime.date(2024, 1, 1),
            period_end=datetime.date(2024, 12, 31),
        )
        creditor = Creditor.objects.create(name="Legacy creditor")
        invoice = Invoice.objects.create(
            creditor=creditor, date=datetime.date(2024, 6, 1), number="INV-LEGACY-1"
        )
        publication = create_publication(apps, "Legacy publication")
        contract = Contract.objects.create(
            name="Legacy contract", publication_billing="Individually"
        )

        pub_row = ReportPublication.objects.create(
            report=report, publication=publication, title="Zebra", publication_type="article"
        )
        ReportInvoice.objects.create(
            report_publication=pub_row, invoice=invoice, invoice_number="INV-2"
        )
        contract_row = ReportContract.objects.create(
            report=report, contract=contract, contract_name="Zebra contract"
        )
        ReportContractInvoice.objects.create(
            report_contract=contract_row, invoice=invoice, invoice_number="INV-2"
        )
        # A second, alphabetically earlier row makes the ordering switch observable.
        second = create_publication(apps, "Second publication")
        ReportPublication.objects.create(
            report=report, publication=second, title="Apple", publication_type="article"
        )

    def test_existing_rows_get_column_defaults(self) -> None:
        apps = self.new_state.apps
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")
        ReportInvoice = apps.get_model("opencost", "OpenCostReportInvoice")
        ReportContract = apps.get_model("opencost", "OpenCostReportContract")
        ReportContractInvoice = apps.get_model("opencost", "OpenCostReportContractInvoice")

        assert ReportPublication.objects.count() == 2
        for row in (
            ReportPublication.objects.get(title="Zebra"),
            ReportInvoice.objects.get(),
            ReportContract.objects.get(),
            ReportContractInvoice.objects.get(),
        ):
            assert row.exported is False
            assert row.had_errors is False
        assert ReportPublication.objects.get(title="Zebra").xml_ordinal is None
        assert ReportContract.objects.get().xml_ordinal is None
        assert ReportInvoice.objects.get().xml_index is None
        assert ReportContractInvoice.objects.get().xml_index is None

    def test_default_ordering_switches_to_id(self) -> None:
        apps = self.new_state.apps
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")

        assert ReportPublication._meta.ordering == ["id"]
        # Insertion order survives; the old title ordering would say ["Apple", "Zebra"].
        assert [row.title for row in ReportPublication.objects.all()] == ["Zebra", "Apple"]

    def test_new_rows_accept_populated_outcome_columns(self) -> None:
        ReportPublication = self.new_state.apps.get_model("opencost", "OpenCostReportPublication")
        row = ReportPublication.objects.get(title="Zebra")
        row.exported = True
        row.had_errors = True
        row.xml_ordinal = 0
        row.save()
        row.refresh_from_db()
        assert (row.exported, row.had_errors, row.xml_ordinal) == (True, True, 0)


@pytest.mark.django_db
class TestSeedOutcomeColumnsReverse(MigratorTestCase):
    """Reverse migration 0013 -> 0012: the outcome columns are dropped and the old
    ordering returns, without error even while they hold populated values."""

    migrate_from = ("opencost", "0013_add_opencost_seed_outcome_columns")
    migrate_to = ("opencost", "0012_add_opencostreport_xml_content_and_issues")

    def prepare(self) -> None:
        """Create rows with the outcome columns populated."""
        apps = self.old_state.apps

        Report = apps.get_model("opencost", "OpenCostReport")
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")
        ReportInvoice = apps.get_model("opencost", "OpenCostReportInvoice")
        ReportContract = apps.get_model("opencost", "OpenCostReportContract")
        ReportContractInvoice = apps.get_model("opencost", "OpenCostReportContractInvoice")
        Contract = apps.get_model("contracts", "Contract")
        Invoice = apps.get_model("invoices", "Invoice")
        Creditor = apps.get_model("invoices", "Creditor")

        report = Report.objects.create(
            title="Generated report",
            period_start=datetime.date(2024, 1, 1),
            period_end=datetime.date(2024, 12, 31),
        )
        creditor = Creditor.objects.create(name="Creditor")
        invoice = Invoice.objects.create(
            creditor=creditor, date=datetime.date(2024, 6, 1), number="INV-1"
        )
        publication = create_publication(apps, "Publication")
        contract = Contract.objects.create(name="Contract", publication_billing="Individually")

        pub_row = ReportPublication.objects.create(
            report=report,
            publication=publication,
            title="Exported publication",
            publication_type="article",
            exported=True,
            had_errors=True,
            xml_ordinal=1,
        )
        ReportInvoice.objects.create(
            report_publication=pub_row,
            invoice=invoice,
            invoice_number="INV-1",
            exported=True,
            xml_index=0,
        )
        contract_row = ReportContract.objects.create(
            report=report,
            contract=contract,
            contract_name="Exported contract",
            exported=True,
            xml_ordinal=2,
        )
        ReportContractInvoice.objects.create(
            report_contract=contract_row,
            invoice=invoice,
            invoice_number="INV-1",
            had_errors=True,
        )

    def test_columns_are_dropped_and_rows_survive(self) -> None:
        apps = self.new_state.apps
        outcome_columns = {"exported", "had_errors", "xml_ordinal", "xml_index"}
        for model_name in SEED_MODELS:
            model = apps.get_model("opencost", model_name)
            field_names = {field.name for field in model._meta.get_fields()}
            assert outcome_columns.isdisjoint(field_names), model_name
            assert model.objects.count() == 1, model_name

    def test_ordering_returns_to_the_snapshot_columns(self) -> None:
        apps = self.new_state.apps
        assert apps.get_model("opencost", "OpenCostReportPublication")._meta.ordering == ["title"]
        assert apps.get_model("opencost", "OpenCostReportInvoice")._meta.ordering == [
            "invoice_number"
        ]
        assert apps.get_model("opencost", "OpenCostReportContract")._meta.ordering == [
            "contract_name"
        ]
        assert apps.get_model("opencost", "OpenCostReportContractInvoice")._meta.ordering == [
            "invoice_number"
        ]

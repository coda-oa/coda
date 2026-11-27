"""Migration 0011 -> 0015: the whole chain runs and the snapshot schema is gone.

Reports prepared while the snapshot tables were the record pass through the document
backfill and the schema drop keeping their artifacts: the stored document, the issue
log and the membership rows. The seven child tables disappear, the survivors keep
membership and outcome columns only, and the issue counts answer from the stored log
alone.
"""

import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase

from coda.apps.opencost.models import OpenCostReport

GOLDENS = Path(__file__).parent / "backfill_goldens"

# The group id the captured clean document carries; reused verbatim so the rebuilt
# snapshot reproduces that document byte for byte.
ALPHA_GROUP_ID = "292e8716-37c6-4c41-a8eb-7c530d234995"

DROPPED_MODELS = (
    "OpenCostReportInstitutionIdentifier",
    "OpenCostReportPublicationLink",
    "OpenCostReportPublicationContract",
    "OpenCostReportInvoicePosition",
    "OpenCostReportContractInstitutionIdentifier",
    "OpenCostReportContractSecondaryIdentifier",
    "OpenCostReportContractInvoicePosition",
)

DROPPED_COLUMNS: dict[str, set[str]] = {
    "opencostreport": {"errors_count", "warnings_count"},
    "opencostreportpublication": {
        "doi",
        "publication_type",
        "journal",
        "external_costsplitting",
        "institution_name",
        "snapshot_date",
    },
    "opencostreportinvoice": {"invoice_number", "creditor", "invoice_date", "snapshot_date"},
    "opencostreportcontract": {
        "contract_name",
        "institution_name",
        "participation_from",
        "participation_to",
        "primary_identifier_value",
        "snapshot_date",
    },
    "opencostreportcontractinvoice": {
        "invoice_number",
        "creditor",
        "invoice_date",
        "amount_invoice",
        "amount_invoice_currency",
        "group_id",
        "snapshot_date",
    },
}


def create_publication(apps: Any, title: str) -> Any:
    """A publication in the historical app state.

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


def create_funding_request(apps: Any, publication: Any) -> Any:
    """A funding request for a publication: a publication issue's fix URL targets it."""
    FundingRequest = apps.get_model("fundingrequests", "FundingRequest")
    FundingRequestReview = apps.get_model("fundingrequests", "FundingRequestReview")

    return FundingRequest.objects.create(
        publication=publication,
        review=FundingRequestReview.objects.create(),
        request_id=f"REQ-{publication.pk}",
        request_date=datetime.date(2024, 1, 1),
        request_number="R-1",
        estimated_cost=Decimal("1000.0000"),
        estimated_cost_currency="EUR",
    )


def create_contract(apps: Any, name: str, *, esac: str | None = None) -> Any:
    Contract = apps.get_model("contracts", "Contract")
    ContractLinkType = apps.get_model("contracts", "ContractLinkType")
    ContractLink = apps.get_model("contracts", "ContractLink")

    contract = Contract.objects.create(name=name, publication_billing="Individually")
    if esac is not None:
        link_type, _ = ContractLinkType.objects.get_or_create(name="ESAC")
        ContractLink.objects.create(contract=contract, type=link_type, value=esac)
    return contract


def create_live_invoice(apps: Any, creditor_name: str, number: str, when: datetime.date) -> Any:
    Creditor = apps.get_model("invoices", "Creditor")
    Invoice = apps.get_model("invoices", "Invoice")

    creditor = Creditor.objects.create(name=creditor_name)
    return Invoice.objects.create(creditor=creditor, date=when, number=number)


def create_live_position(
    apps: Any,
    invoice: Any,
    cost_type: str,
    *,
    publication: Any = None,
    contract: Any = None,
) -> Any:
    """A live position to hang a snapshot position off; only the snapshot is read."""
    Position = apps.get_model("invoices", "Position")

    return Position.objects.create(
        invoice=invoice,
        publication=publication,
        contract=contract,
        description="fixture position",
        cost_amount=Decimal("1500.0000"),
        cost_currency="EUR",
        cost_type=cost_type,
        tax_rate=Decimal("0.1900"),
    )


@pytest.mark.django_db
class TestDropSnapshotChildrenForward(MigratorTestCase):
    """Forward chain 0011 -> 0015: snapshots backfill, then the schema shrinks.

    One report carries the full snapshot tree of an exported publication and contract -
    the chain backfills its document cleanly and its log stays empty; the other carries
    a publication that backfill excludes for lacking institution data, so its log holds
    one error. Both artifacts must come out of 0015 unharmed.
    """

    migrate_from = ("opencost", "0011_remove_opencostreport_xml_content")
    migrate_to = ("opencost", "0015_drop_opencost_snapshot_children")

    def prepare(self) -> None:
        apps = self.old_state.apps
        self._seed_clean(apps)
        self._seed_excluded(apps)

    # --- fixtures ------------------------------------------------------------------

    def _create_report(self, apps: Any, title: str, start: int, end: int) -> Any:
        Report = apps.get_model("opencost", "OpenCostReport")
        return Report.objects.create(
            title=title,
            period_start=datetime.date(start, 1, 1),
            period_end=datetime.date(end, 12, 31),
        )

    def _seed_clean(self, apps: Any) -> None:
        """A publication with its invoice, ESAC contract and shared group id."""
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")
        InstitutionIdentifier = apps.get_model("opencost", "OpenCostReportInstitutionIdentifier")
        PublicationLink = apps.get_model("opencost", "OpenCostReportPublicationLink")
        PublicationContract = apps.get_model("opencost", "OpenCostReportPublicationContract")
        ReportInvoice = apps.get_model("opencost", "OpenCostReportInvoice")
        InvoicePosition = apps.get_model("opencost", "OpenCostReportInvoicePosition")
        ReportContract = apps.get_model("opencost", "OpenCostReportContract")
        SecondaryIdentifier = apps.get_model(
            "opencost", "OpenCostReportContractSecondaryIdentifier"
        )
        ReportContractInvoice = apps.get_model("opencost", "OpenCostReportContractInvoice")
        ContractInvoicePosition = apps.get_model(
            "opencost", "OpenCostReportContractInvoicePosition"
        )

        report = self._create_report(apps, "Clean fixture", 2024, 2024)
        publication = create_publication(apps, "Live alpha")
        contract = create_contract(apps, "Live contract one", esac="esac-fixture-one-001")

        pub_invoice = create_live_invoice(
            apps, "Fixture Publisher One", "INV-FIX-A-001", datetime.date(2024, 6, 15)
        )
        pub_position = create_live_position(apps, pub_invoice, "gold-oa", publication=publication)
        contract_invoice = create_live_invoice(
            apps, "Contract Creditor Fix", "INV-FIX-C-001", datetime.date(2024, 7, 1)
        )
        contract_positions = [
            create_live_position(apps, contract_invoice, "publish", contract=contract)
            for _ in range(2)
        ]

        pub_row = ReportPublication.objects.create(
            report=report,
            publication=publication,
            title="Fixture Publication Alpha",
            doi="10.1234/5678",
            publication_type="conference paper",
            publisher="Fixture Publisher Press",
            journal="Journal of Fixture Testing",
            external_costsplitting=False,
            institution_name="Affiliated Testing Institution",
        )
        InstitutionIdentifier.objects.create(
            report_publication=pub_row,
            identifier_type="ror",
            value="https://ror.org/fixture-alpha",
        )
        for link_type, value in (
            ("handle", "hdl:fixture/alpha"),
            ("isbn", "978-3-16-148410-0"),
            ("urn", "urn:fixture:alpha"),
        ):
            PublicationLink.objects.create(
                report_publication=pub_row, link_type=link_type, value=value
            )
        PublicationContract.objects.create(
            report_publication=pub_row,
            contract=contract,
            contract_year=2024,
            group_id=ALPHA_GROUP_ID,
        )
        pub_invoice_row = ReportInvoice.objects.create(
            report_publication=pub_row,
            invoice=pub_invoice,
            invoice_number="INV-FIX-A-001",
            creditor="Fixture Publisher One",
            invoice_date=datetime.date(2024, 6, 15),
        )
        InvoicePosition.objects.create(
            report_invoice=pub_invoice_row,
            position=pub_position,
            amount=Decimal("1500.0000"),
            currency="EUR",
            cost_type="gold-oa",
            vat=Decimal("285.0000"),
        )

        contract_row = ReportContract.objects.create(
            report=report,
            contract=contract,
            contract_name="Fixture Contract One",
            institution_name="Fixture Home Institution",
            participation_from=datetime.date(2024, 1, 1),
            participation_to=datetime.date(2024, 12, 31),
            primary_identifier_value="esac-fixture-one-001",
        )
        SecondaryIdentifier.objects.create(
            report_contract=contract_row,
            identifier_type="oai",
            value="oai-fixture-one",
        )
        contract_invoice_row = ReportContractInvoice.objects.create(
            report_contract=contract_row,
            invoice=contract_invoice,
            invoice_number="INV-FIX-C-001",
            creditor="Contract Creditor Fix",
            invoice_date=datetime.date(2024, 7, 1),
            amount_invoice=Decimal("2000.0000"),
            amount_invoice_currency="EUR",
            group_id=ALPHA_GROUP_ID,
        )
        for position, amount, vat in (
            (contract_positions[0], "800.0000", "152.0000"),
            (contract_positions[1], "1200.0000", "228.0000"),
        ):
            ContractInvoicePosition.objects.create(
                report_contract_invoice=contract_invoice_row,
                position=position,
                amount=Decimal(amount),
                currency="EUR",
                cost_type="publish",
                vat=Decimal(vat),
            )

    def _seed_excluded(self, apps: Any) -> None:
        """One publication whose snapshot holds no institution at all."""
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")
        PublicationLink = apps.get_model("opencost", "OpenCostReportPublicationLink")
        ReportInvoice = apps.get_model("opencost", "OpenCostReportInvoice")
        InvoicePosition = apps.get_model("opencost", "OpenCostReportInvoicePosition")

        report = self._create_report(apps, "Excluded fixture", 2025, 2025)
        publication = create_publication(apps, "Live beta")
        create_funding_request(apps, publication)

        invoice = create_live_invoice(
            apps, "Orphan Creditor", "INV-FIX-B-001", datetime.date(2025, 3, 1)
        )
        position = create_live_position(apps, invoice, "gold-oa", publication=publication)

        pub_row = ReportPublication.objects.create(
            report=report,
            publication=publication,
            title="Orphan Publication Beta",
            doi="10.1234/5678",
            publication_type="conference paper",
            publisher="Fixture Publisher Press",
            journal="Journal of Fixture Testing",
            external_costsplitting=False,
            institution_name="",
        )
        PublicationLink.objects.create(
            report_publication=pub_row,
            link_type="isbn",
            value="978-3-16-148410-0",
        )
        invoice_row = ReportInvoice.objects.create(
            report_publication=pub_row,
            invoice=invoice,
            invoice_number="INV-FIX-B-001",
            creditor="Orphan Creditor",
            invoice_date=datetime.date(2025, 3, 1),
        )
        InvoicePosition.objects.create(
            report_invoice=invoice_row,
            position=position,
            amount=Decimal("900.0000"),
            currency="EUR",
            cost_type="gold-oa",
            vat=Decimal("0.0000"),
        )

    # --- assertions ----------------------------------------------------------------

    def test_child_tables_are_gone(self) -> None:
        opencost_models = set(self.new_state.apps.all_models["opencost"])
        for name in DROPPED_MODELS:
            assert name.lower() not in opencost_models, name

    def test_survivors_lost_the_snapshot_columns(self) -> None:
        for model_name, dropped in DROPPED_COLUMNS.items():
            model = self.new_state.apps.get_model("opencost", model_name)
            field_names = {field.name for field in model._meta.get_fields()}
            assert dropped.isdisjoint(field_names), model_name

    def test_survivors_kept_membership_and_outcome_columns(self) -> None:
        apps = self.new_state.apps

        report_fields = {
            f.name for f in apps.get_model("opencost", "OpenCostReport")._meta.get_fields()
        }
        assert {"xml_content", "issues"} <= report_fields

        publication = apps.get_model("opencost", "OpenCostReportPublication")
        publication_fields = {f.name for f in publication._meta.get_fields()}
        assert {
            "report",
            "publication",
            "title",
            "publisher",
            "exported",
            "had_errors",
            "xml_ordinal",
        } <= publication_fields

        invoice = apps.get_model("opencost", "OpenCostReportInvoice")
        invoice_fields = {f.name for f in invoice._meta.get_fields()}
        assert {
            "report_publication",
            "invoice",
            "exported",
            "had_errors",
            "xml_index",
        } <= invoice_fields

        contract = apps.get_model("opencost", "OpenCostReportContract")
        contract_fields = {f.name for f in contract._meta.get_fields()}
        assert {"report", "contract", "exported", "had_errors", "xml_ordinal"} <= contract_fields

        contract_invoice = apps.get_model("opencost", "OpenCostReportContractInvoice")
        contract_invoice_fields = {f.name for f in contract_invoice._meta.get_fields()}
        assert {
            "report_contract",
            "invoice",
            "exported",
            "had_errors",
            "xml_index",
        } <= contract_invoice_fields

    def test_membership_rows_survive(self) -> None:
        apps = self.new_state.apps
        assert apps.get_model("opencost", "OpenCostReport").objects.count() == 2
        assert apps.get_model("opencost", "OpenCostReportPublication").objects.count() == 2
        assert apps.get_model("opencost", "OpenCostReportInvoice").objects.count() == 2
        assert apps.get_model("opencost", "OpenCostReportContract").objects.count() == 1
        assert apps.get_model("opencost", "OpenCostReportContractInvoice").objects.count() == 1

    def test_backfilled_document_survives_the_drop(self) -> None:
        Report = self.new_state.apps.get_model("opencost", "OpenCostReport")
        clean = Report.objects.get(title="Clean fixture")
        assert clean.xml_content == (GOLDENS / "clean.xml").read_text(encoding="utf-8")
        assert clean.issues == []

        excluded = Report.objects.get(title="Excluded fixture")
        assert excluded.xml_content == (GOLDENS / "excluded.xml").read_text(encoding="utf-8")
        assert [issue["level"] for issue in excluded.issues] == ["error"]
        assert [issue["entity_type"] for issue in excluded.issues] == ["global"]
        assert [issue["entity_name"] for issue in excluded.issues] == ["Orphan Publication Beta"]

    def test_backfilled_row_outcomes_survive_the_drop(self) -> None:
        apps = self.new_state.apps
        clean = apps.get_model("opencost", "OpenCostReport").objects.get(title="Clean fixture")

        publication = apps.get_model("opencost", "OpenCostReportPublication").objects.get(
            report=clean
        )
        contract = apps.get_model("opencost", "OpenCostReportContract").objects.get(report=clean)
        assert (publication.exported, publication.had_errors, publication.xml_ordinal) == (
            True,
            False,
            0,
        )
        assert (contract.exported, contract.had_errors, contract.xml_ordinal) == (
            True,
            False,
            0,
        )

    def test_issue_counts_answer_from_the_stored_json(self) -> None:
        """The live application model reads the chain's artifacts with no other source.

        ``OpenCostReport`` here is the current ``models.py`` class, not a historical
        state - the database schema it faces is the one this migration left behind.
        """
        clean = OpenCostReport.objects.get(title="Clean fixture")
        assert clean.get_issue_counts() == {"errors": 0, "warnings": 0}
        assert clean.has_issues() is False

        excluded = OpenCostReport.objects.get(title="Excluded fixture")
        assert excluded.get_issue_counts() == {"errors": 1, "warnings": 0}
        assert excluded.has_issues() is True
        assert excluded.xml_content == (GOLDENS / "excluded.xml").read_text(encoding="utf-8")

"""Migration 0013 -> 0014: every legacy report gains the document its snapshot tree describes.

The goldens under ``backfill_goldens/`` are the byte-for-byte output the snapshot-era
transform produced from the exact fixture data ``prepare`` rebuilds; only entity ids
differ per test database, so the expected issue log adopts the id the fixture got.
"""

import datetime
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase

GOLDENS = Path(__file__).parent / "backfill_goldens"

# The group ids the captured reports' documents carry; reused verbatim so the
# rebuilt snapshots reproduce those documents byte for byte.
ALPHA_GROUP_ID = "292e8716-37c6-4c41-a8eb-7c530d234995"
GAMMA_GROUP_ID = "8b498d39-7537-4e65-b6e1-6018b970caf8"

# The untouched report's stored artifact, as written before the migration ran.
PRESERVED_XML = "<data>already generated</data>"
PRESERVED_ISSUES = [{"level": "error", "message": "pre-existing"}]


def golden(name: str) -> str:
    return (GOLDENS / f"{name}.xml").read_text(encoding="utf-8")


def golden_issues(name: str, entity_id: int) -> list[dict[str, Any]]:
    """The captured issue log with the entity id this database assigned to the record."""
    issues: list[dict[str, Any]] = json.loads(
        (GOLDENS / f"{name}.issues.json").read_text(encoding="utf-8")
    )
    for issue in issues:
        issue["entity_id"] = entity_id
        fix_url = issue["fix_url"]
        if fix_url:
            issue["fix_url"] = re.sub(r"/\d+/", f"/{entity_id}/", fix_url)
    return issues


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
class TestBackfillOpenCostXmlForward(MigratorTestCase):
    """Forward migration 0013 -> 0014: snapshot trees become stored artifacts.

    Five reports cover the matrix: one whose whole tree transforms cleanly, one whose
    only publication is excluded for lacking institution data, one whose contract is
    exported degraded (a position with an unacceptable cost type dropped), one whose
    stored document is already filled, and one whose snapshot references a funding
    request that no longer exists.
    """

    migrate_from = ("opencost", "0013_add_opencost_seed_outcome_columns")
    migrate_to = ("opencost", "0014_backfill_opencost_xml")

    def prepare(self) -> None:
        apps = self.old_state.apps
        self._seed_clean(apps)
        self._seed_excluded(apps)
        self._seed_degraded(apps)
        self._seed_untouched(apps)
        self._seed_poisoned(apps)

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

    def _seed_degraded(self, apps: Any) -> None:
        """A contract whose one invoice loses an unacceptable-cost-type position."""
        ReportContract = apps.get_model("opencost", "OpenCostReportContract")
        ReportContractInvoice = apps.get_model("opencost", "OpenCostReportContractInvoice")
        ContractInvoicePosition = apps.get_model(
            "opencost", "OpenCostReportContractInvoicePosition"
        )

        report = self._create_report(apps, "Degraded fixture", 2026, 2026)
        contract = create_contract(apps, "Live contract gamma")

        invoice = create_live_invoice(
            apps, "Gamma Creditor", "INV-FIX-G-001", datetime.date(2026, 2, 10)
        )
        bogus = create_live_position(apps, invoice, "bogus-service", contract=contract)
        valid = create_live_position(apps, invoice, "publish", contract=contract)

        contract_row = ReportContract.objects.create(
            report=report,
            contract=contract,
            contract_name="Fixture Contract Gamma",
            institution_name="Fixture Home Institution Two",
            participation_from=datetime.date(2026, 1, 1),
            participation_to=datetime.date(2026, 12, 31),
            primary_identifier_value="esac-fixture-gamma-003",
        )
        invoice_row = ReportContractInvoice.objects.create(
            report_contract=contract_row,
            invoice=invoice,
            invoice_number="INV-FIX-G-001",
            creditor="Gamma Creditor",
            invoice_date=datetime.date(2026, 2, 10),
            amount_invoice=Decimal("800.0000"),
            amount_invoice_currency="EUR",
            group_id=GAMMA_GROUP_ID,
        )
        for position, amount, cost_type, vat in (
            (bogus, "300.0000", "bogus-service", "57.0000"),
            (valid, "500.0000", "publish", "95.0000"),
        ):
            ContractInvoicePosition.objects.create(
                report_contract_invoice=invoice_row,
                position=position,
                amount=Decimal(amount),
                currency="EUR",
                cost_type=cost_type,
                vat=Decimal(vat),
            )

    def _seed_untouched(self, apps: Any) -> None:
        """A report whose stored document is already filled: not the backfill's to touch."""
        Report = apps.get_model("opencost", "OpenCostReport")
        Report.objects.create(
            title="Already generated fixture",
            period_start=datetime.date(2023, 1, 1),
            period_end=datetime.date(2023, 12, 31),
            xml_content=PRESERVED_XML,
            issues=PRESERVED_ISSUES,
            errors_count=1,
            warnings_count=0,
        )

    def _seed_poisoned(self, apps: Any) -> None:
        """A snapshot whose publication lost the funding request its issues link to.

        The publication is otherwise exportable in shape - it has an institution - but it
        carries no cost data, so reporting the exclusion has to build a fix URL through
        the funding request, and resolving it fails.
        """
        ReportPublication = apps.get_model("opencost", "OpenCostReportPublication")

        report = self._create_report(apps, "Poisoned fixture", 2027, 2027)
        publication = create_publication(apps, "Live epsilon")
        ReportPublication.objects.create(
            report=report,
            publication=publication,
            title="Homeless Publication Delta",
            doi="10.1234/5678",
            publication_type="conference paper",
            publisher="Fixture Publisher Press",
            journal="Journal of Fixture Testing",
            external_costsplitting=False,
            institution_name="Institution With Fading Track",
        )

    # --- assertions ----------------------------------------------------------------

    def _report(self, apps: Any, title: str) -> Any:
        return apps.get_model("opencost", "OpenCostReport").objects.get(title=title)

    def test_clean_report_document_matches_golden(self) -> None:
        report = self._report(self.new_state.apps, "Clean fixture")
        assert report.xml_content == golden("clean")
        assert report.issues == []
        assert (report.errors_count, report.warnings_count) == (0, 0)

    def test_clean_report_row_outcomes(self) -> None:
        apps = self.new_state.apps
        report = self._report(apps, "Clean fixture")

        publication = apps.get_model("opencost", "OpenCostReportPublication").objects.get(
            report=report
        )
        contract = apps.get_model("opencost", "OpenCostReportContract").objects.get(report=report)
        pub_invoice = publication.invoices.get()
        contract_invoice = contract.invoices.get()

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
        assert (
            pub_invoice.exported,
            pub_invoice.had_errors,
            pub_invoice.xml_index,
        ) == (True, False, 0)
        assert (
            contract_invoice.exported,
            contract_invoice.had_errors,
            contract_invoice.xml_index,
        ) == (True, False, 0)

    def test_excluded_report_document_matches_golden(self) -> None:
        apps = self.new_state.apps
        report = self._report(apps, "Excluded fixture")
        publication = apps.get_model("opencost", "OpenCostReportPublication").objects.get(
            report=report
        )

        assert report.xml_content == golden("excluded")
        assert report.issues == golden_issues("excluded", publication.publication_id)
        assert (report.errors_count, report.warnings_count) == (1, 0)

        assert (publication.exported, publication.had_errors, publication.xml_ordinal) == (
            False,
            True,
            None,
        )
        invoice = publication.invoices.get()
        assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (
            False,
            True,
            None,
        )

    def test_degraded_report_document_matches_golden(self) -> None:
        apps = self.new_state.apps
        report = self._report(apps, "Degraded fixture")
        contract = apps.get_model("opencost", "OpenCostReportContract").objects.get(report=report)

        assert report.xml_content == golden("degraded")
        assert report.issues == golden_issues("degraded", contract.contract_id)
        assert (report.errors_count, report.warnings_count) == (1, 0)

        assert (contract.exported, contract.had_errors, contract.xml_ordinal) == (
            True,
            True,
            0,
        )
        invoice = contract.invoices.get()
        assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (
            True,
            True,
            0,
        )

    def test_report_with_stored_document_is_untouched(self) -> None:
        report = self._report(self.new_state.apps, "Already generated fixture")
        assert report.xml_content == PRESERVED_XML
        assert report.issues == PRESERVED_ISSUES
        assert (report.errors_count, report.warnings_count) == (1, 0)

    def test_untransformable_report_is_skipped_and_later_ones_still_backfill(self) -> None:
        """A failing snapshot rolls back to empty and does not stop the run."""
        apps = self.new_state.apps
        report = self._report(apps, "Poisoned fixture")
        publication = apps.get_model("opencost", "OpenCostReportPublication").objects.get(
            report=report
        )

        assert report.xml_content == ""
        assert report.issues == []
        assert (report.errors_count, report.warnings_count) == (0, 0)
        assert (publication.exported, publication.had_errors, publication.xml_ordinal) == (
            False,
            False,
            None,
        )

        # The poisoned report is the last one; the reports before it kept their work.
        clean = self._report(apps, "Clean fixture")
        assert clean.xml_content == golden("clean")

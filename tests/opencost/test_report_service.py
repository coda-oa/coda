import pytest

from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportInvoice,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
)
from coda.apps.publications.models._attachedentities import PublicationAttachedConcept
from coda.apps.publications.models._links import Link, LinkType
from coda.apps.publications.models._vocabulary import Vocabulary
from tests import modelfactory
from tests.opencost.helpers import create_publication_with_invoice, create_opencost_report
from datetime import date
from decimal import Decimal
from tests.opencost.helpers import create_creditor, create_invoice, create_position


@pytest.mark.django_db
def test__time_period__generate_report__creates_report_record() -> None:
    period_start = date(2024, 1, 1)
    period_end = date(2024, 12, 31)

    report = create_opencost_report(
        title="Test Report 2024", period_start=period_start, period_end=period_end
    )

    saved_report = OpenCostReport.objects.get(pk=report.pk)
    assert saved_report.title == "Test Report 2024"
    assert saved_report.period_start == period_start
    assert saved_report.period_end == period_end


@pytest.mark.django_db
def test__full_publication_with_invoice_data__generate_report__creates_report_publication_snapshot() -> (
    None
):
    publication = modelfactory.publication(title="Test Publication")
    publication.online_publication_date = date(2024, 6, 1)
    publication.save()

    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    Link.objects.create(
        publication=publication,
        type=doi_type,
        value="10.1234/test.doi",
    )
    vocabulary = Vocabulary.objects.create(name="COAR", version="1.0")

    coar_concept = PublicationAttachedConcept.objects.create(
        vocabulary=vocabulary, name="conference paper"
    )
    publication.publication_type = coar_concept
    publication.save()

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
        creditor_name="Test Creditor",
    )

    report = create_opencost_report(title="Test Report with Publication 2024")

    assert OpenCostReportPublication.objects.filter(report=report).exists()

    report_publication = OpenCostReportPublication.objects.get(report=report)

    assert report_publication.title == "Test Publication"
    assert report_publication.doi == "10.1234/test.doi"
    assert report_publication.publication_type == "conference paper"
    assert publication.article_journal is not None
    assert report_publication.publisher == publication.article_journal.publisher.name
    assert report_publication.journal == publication.article_journal.title

    # TODO external_costsplitting - we'll implement this later with cost sharing
    assert report_publication.external_costsplitting is None


@pytest.mark.django_db
def test__publication_with_invoice_data__generate_report__creates_report_invoice_snapshot() -> None:
    publication = modelfactory.publication(title="Invoice Test Publication")
    publication.online_publication_date = date(2024, 5, 15)
    publication.save()

    invoice, _ = create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
    )

    report = create_opencost_report(title="Test Report with Invoice 2024")

    report_publication = OpenCostReportPublication.objects.get(report=report)
    report_invoice = OpenCostReportInvoice.objects.get(report_publication=report_publication)
    assert OpenCostReportInvoice.objects.filter(report_publication=report_publication).exists()

    assert report_invoice.invoice == invoice
    assert report_invoice.invoice_number == "INV-2024-001"
    assert report_invoice.creditor == "Invoice Creditor"
    assert report_invoice.invoice_date == date(2024, 6, 1)


@pytest.mark.django_db
def test__invoice_with_positions__generate_report__creates_report_invoice_position_snapshots() -> (
    None
):
    publication = modelfactory.publication(title="Invoice Position Test Publication")
    publication.online_publication_date = date(2024, 4, 20)
    publication.save()

    creditor = create_creditor(name="Position Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-2024-002"
    )

    create_position(
        invoice=invoice,
        publication=publication,
        description="APC part 1",
        cost_amount=Decimal("1000.00"),
    )
    create_position(
        invoice=invoice,
        publication=publication,
        description="APC part 2",
        cost_amount=Decimal("500.00"),
    )

    report = create_opencost_report(title="Test Report with Invoice Positions 2024")

    report_publication = OpenCostReportPublication.objects.get(report=report)
    report_invoice = OpenCostReportInvoice.objects.get(report_publication=report_publication)

    oc_positions = OpenCostReportInvoicePosition.objects.filter(report_invoice=report_invoice)
    assert oc_positions.count() == 2

    amounts = [pos.amount for pos in oc_positions]
    assert Decimal("1000.00") in amounts
    assert Decimal("500.00") in amounts

    vat_values = [pos.vat for pos in oc_positions]
    assert Decimal("190.00") in vat_values
    assert Decimal("95.00") in vat_values

    for position in oc_positions:
        assert position.currency == "EUR"
        assert position.cost_type == "gold-oa"


@pytest.mark.django_db
def test__publication_with_multiple_invoices__generate_report__creates_multiple_report_invoice_snapshots() -> (
    None
):
    publication = modelfactory.publication(title="Multiple Invoices Publication")
    publication.online_publication_date = date(2024, 3, 10)
    publication.save()

    creditor1 = create_creditor(name="Creditor One")
    invoice1 = create_invoice(
        creditor=creditor1, invoice_date=date(2024, 4, 1), number="INV-2024-101"
    )
    create_position(
        invoice=invoice1,
        publication=publication,
        description="APC part 1",
        cost_amount=Decimal("800.00"),
    )

    creditor2 = create_creditor(name="Creditor Two")
    invoice2 = create_invoice(
        creditor=creditor2, invoice_date=date(2024, 4, 15), number="INV-2024-102"
    )
    create_position(
        invoice=invoice2,
        publication=publication,
        description="APC part 2",
        cost_amount=Decimal("700.00"),
    )

    report = create_opencost_report(title="Test Report with Multiple Invoices 2024")

    report_publication = OpenCostReportPublication.objects.get(report=report)
    oc_invoices = OpenCostReportInvoice.objects.filter(report_publication=report_publication)
    assert oc_invoices.count() == 2

    invoice_numbers = [inv.invoice_number for inv in oc_invoices]
    assert "INV-2024-101" in invoice_numbers
    assert "INV-2024-102" in invoice_numbers


@pytest.mark.django_db
def test__publication_with_invoice_outside_period__generate_report__publication_not_included() -> (
    None
):
    publication = modelfactory.publication(title="Outside Period Publication")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2023, 11, 30),
        invoice_number="INV-2023-999",
        creditor_name="Outside Period Creditor",
        cost_amount=Decimal("1200.00"),
    )

    report = create_opencost_report(
        title="Test Report Excluding Outside Period Publication",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )

    assert not OpenCostReportPublication.objects.filter(
        report=report, publication=publication
    ).exists()


@pytest.mark.django_db
def test__multiple_publications_with_invoices__generate_report__all_included() -> None:
    publication1 = modelfactory.publication(title="Publication One")
    publication1.online_publication_date = date(2024, 2, 5)
    publication1.save()

    create_publication_with_invoice(
        publication1,
        invoice_date=date(2024, 3, 1),
        invoice_number="INV-2024-201",
        creditor_name="Creditor One",
        cost_amount=Decimal("900.00"),
    )

    publication2 = modelfactory.publication(title="Publication Two")
    publication2.online_publication_date = date(2024, 3, 15)
    publication2.save()

    create_publication_with_invoice(
        publication2,
        invoice_date=date(2024, 4, 10),
        invoice_number="INV-2024-202",
        creditor_name="Creditor Two",
        cost_amount=Decimal("1100.00"),
    )

    report = create_opencost_report(title="Test Report with Multiple Publications 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=publication1
    ).exists()
    assert OpenCostReportPublication.objects.filter(
        report=report, publication=publication2
    ).exists()


@pytest.mark.django_db
def test__publication_with_secondary_identifiers__generate_report__link_snapshots_created_and_immutable() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Links")
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    handle_link = Link.objects.create(
        publication=publication, type=handle_type, value="hdl:1234/original"
    )
    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    urn_link = Link.objects.create(
        publication=publication, type=urn_type, value="urn:nbn:de:original"
    )
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None

    link_snapshots = report_publication.links.all()
    assert link_snapshots.count() == 2

    handle_snapshot = link_snapshots.filter(link_type="handle").first()
    assert handle_snapshot is not None
    assert handle_snapshot.value == "hdl:1234/original"

    urn_snapshot = link_snapshots.filter(link_type="urn").first()
    assert urn_snapshot is not None
    assert urn_snapshot.value == "urn:nbn:de:original"

    handle_link.value = "hdl:1234/CHANGED"
    handle_link.save()
    urn_link.delete()

    link_snapshots_after = report_publication.links.all()
    assert link_snapshots_after.count() == 2

    handle_snapshot_after = link_snapshots_after.filter(link_type="handle").first()
    assert handle_snapshot_after is not None
    assert handle_snapshot_after.value == "hdl:1234/original"

    urn_snapshot_after = link_snapshots_after.filter(link_type="urn").first()
    assert urn_snapshot_after is not None
    assert urn_snapshot_after.value == "urn:nbn:de:original"


@pytest.mark.django_db
def test__publication_with_invoices_inside_and_outside_period__generate_report__only_period_invoices_snapshotted() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Multiple Period Invoices")

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 4, 15),
        invoice_number="INV-Q2-001",
        creditor_name="Creditor A",
        cost_amount=Decimal("1000.00"),
    )

    creditor_b = create_creditor(name="Creditor B")
    invoice_2 = create_invoice(
        creditor=creditor_b, invoice_date=date(2024, 5, 20), number="INV-Q2-002"
    )
    create_position(invoice_2, publication, cost_amount=Decimal("1500.00"))

    creditor_c = create_creditor(name="Creditor C")
    invoice_3 = create_invoice(
        creditor=creditor_c, invoice_date=date(2024, 7, 10), number="INV-Q3-001"
    )
    create_position(invoice_3, publication, cost_amount=Decimal("2000.00"))

    report = create_opencost_report(
        title="Q2 2024 Report",
        period_start=date(2024, 4, 1),
        period_end=date(2024, 6, 30),
    )

    report_publication = report.publications.first()
    assert report_publication is not None
    assert report_publication.publication == publication

    invoice_snapshots = report_publication.invoices.all()
    assert invoice_snapshots.count() == 2

    invoice_numbers = {inv.invoice_number for inv in invoice_snapshots}
    assert "INV-Q2-001" in invoice_numbers
    assert "INV-Q2-002" in invoice_numbers
    assert "INV-Q3-001" not in invoice_numbers

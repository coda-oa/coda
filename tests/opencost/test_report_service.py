from datetime import date
from decimal import Decimal
import pytest

from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportInvoice,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
)
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.opencost.report_service import generate_report
from coda.apps.publications.models._attachedentities import (
    AttachedContract,
    PublicationAttachedConcept,
)
from coda.apps.publications.models._links import Link, LinkType
from coda.apps.publications.models._vocabulary import Vocabulary
from tests import modelfactory
from tests.opencost.helpers import (
    create_creditor,
    create_invoice,
    create_position,
    create_publication_with_invoice,
    create_opencost_report,
    create_institution_with_identifiers,
    create_corresponding_author,
    create_contract_with_identifiers,
)
from coda.apps.institutions.models import Institution, InstitutionLinkType, InstitutionLink


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
def test__filters_provided__generate_report__persists_filters_on_report() -> None:
    filters = {
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "payment_status": "paid,unpaid",
        "contract_name": "1",
    }

    report = generate_report(title="Test Report Filters", filters=filters)

    saved_report = OpenCostReport.objects.get(pk=report.pk)
    assert saved_report.filters["payment_status"] == ["paid", "unpaid"]
    assert saved_report.filters["contract_name"] == 1


@pytest.mark.django_db
def test__full_publication_with_invoice_data__generate_report__creates_report_publication_snapshot() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.external_costsplitting = False
    fr.save()

    vocabulary = Vocabulary.objects.create(name="COAR", version="1.0")

    coar_concept = PublicationAttachedConcept.objects.create(
        vocabulary=vocabulary, name="conference paper"
    )
    fr.publication.publication_type = coar_concept
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
        creditor_name="Test Creditor",
    )

    report = create_opencost_report(title="Test Report with Publication 2024")

    assert OpenCostReportPublication.objects.filter(report=report).exists()

    report_publication = OpenCostReportPublication.objects.get(report=report)

    assert report_publication.title == "Test Publication"
    assert report_publication.doi == "10.1234/5678"  # domainfactory default DOI
    assert report_publication.publication_type == "conference paper"
    assert fr.publication.article_journal is not None
    assert report_publication.publisher == fr.publication.article_journal.publisher.name
    assert report_publication.journal == fr.publication.article_journal.title
    assert report_publication.external_costsplitting is False


@pytest.mark.django_db
def test__publication_with_invoice_data__generate_report__creates_report_invoice_snapshot() -> None:
    fr = modelfactory.fundingrequest(title="Invoice Test Publication")
    fr.publication.online_publication_date = date(2024, 5, 15)
    fr.publication.save()

    invoice, _ = create_publication_with_invoice(
        fr.publication,
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
    fr = modelfactory.fundingrequest(title="Invoice Position Test Publication")
    fr.publication.online_publication_date = date(2024, 4, 20)
    fr.publication.save()

    creditor = create_creditor(name="Position Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-2024-002"
    )

    create_position(
        invoice=invoice,
        publication=fr.publication,
        description="APC part 1",
        cost_amount=Decimal("1000.00"),
    )
    create_position(
        invoice=invoice,
        publication=fr.publication,
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
    fr = modelfactory.fundingrequest(title="Multiple Invoices Publication")
    fr.publication.online_publication_date = date(2024, 3, 10)
    fr.publication.save()

    creditor1 = create_creditor(name="Creditor One")
    invoice1 = create_invoice(
        creditor=creditor1, invoice_date=date(2024, 4, 1), number="INV-2024-101"
    )
    create_position(
        invoice=invoice1,
        publication=fr.publication,
        description="APC part 1",
        cost_amount=Decimal("800.00"),
    )

    creditor2 = create_creditor(name="Creditor Two")
    invoice2 = create_invoice(
        creditor=creditor2, invoice_date=date(2024, 4, 15), number="INV-2024-102"
    )
    create_position(
        invoice=invoice2,
        publication=fr.publication,
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
    fr = modelfactory.fundingrequest(title="Outside Period Publication")

    create_publication_with_invoice(
        fr.publication,
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
        report=report, publication=fr.publication
    ).exists()


@pytest.mark.django_db
def test__multiple_publications_with_invoices__generate_report__all_included() -> None:
    fr1 = modelfactory.fundingrequest(title="Publication One")
    fr1.publication.online_publication_date = date(2024, 2, 5)
    fr1.publication.save()

    create_publication_with_invoice(
        fr1.publication,
        invoice_date=date(2024, 3, 1),
        invoice_number="INV-2024-201",
        creditor_name="Creditor One",
        cost_amount=Decimal("900.00"),
    )

    fr2 = modelfactory.fundingrequest(title="Publication Two")
    fr2.publication.online_publication_date = date(2024, 3, 15)
    fr2.publication.save()

    create_publication_with_invoice(
        fr2.publication,
        invoice_date=date(2024, 4, 10),
        invoice_number="INV-2024-202",
        creditor_name="Creditor Two",
        cost_amount=Decimal("1100.00"),
    )

    report = create_opencost_report(title="Test Report with Multiple Publications 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr1.publication
    ).exists()
    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr2.publication
    ).exists()


@pytest.mark.django_db
def test__publication_with_secondary_identifiers__generate_report__link_snapshots_created_and_immutable() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with Links")
    # Factory creates DOI and ISBN - we add Handle and URN
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    handle_link = Link.objects.create(
        publication=fr.publication, type=handle_type, value="hdl:1234/original"
    )
    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    urn_link = Link.objects.create(
        publication=fr.publication, type=urn_type, value="urn:nbn:de:original"
    )
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None

    link_snapshots = report_publication.links.all()
    assert link_snapshots.count() == 3  # ISBN (factory) + Handle + URN (DOI stored separately)

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
    assert link_snapshots_after.count() == 3  # Snapshots are immutable

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
    fr = modelfactory.fundingrequest(title="Publication with Multiple Period Invoices")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 4, 15),
        invoice_number="INV-Q2-001",
        creditor_name="Creditor A",
        cost_amount=Decimal("1000.00"),
    )

    creditor_b = create_creditor(name="Creditor B")
    invoice_2 = create_invoice(
        creditor=creditor_b, invoice_date=date(2024, 5, 20), number="INV-Q2-002"
    )
    create_position(invoice_2, fr.publication, cost_amount=Decimal("1500.00"))

    creditor_c = create_creditor(name="Creditor C")
    invoice_3 = create_invoice(
        creditor=creditor_c, invoice_date=date(2024, 7, 10), number="INV-Q3-001"
    )
    create_position(invoice_3, fr.publication, cost_amount=Decimal("2000.00"))

    report = create_opencost_report(
        title="Q2 2024 Report",
        period_start=date(2024, 4, 1),
        period_end=date(2024, 6, 30),
    )

    report_publication = report.publications.first()
    assert report_publication is not None
    assert report_publication.publication == fr.publication

    invoice_snapshots = report_publication.invoices.all()
    assert invoice_snapshots.count() == 2

    invoice_numbers = {inv.invoice_number for inv in invoice_snapshots}
    assert "INV-Q2-001" in invoice_numbers
    assert "INV-Q2-002" in invoice_numbers
    assert "INV-Q3-001" not in invoice_numbers


@pytest.mark.django_db
def test__publication_with_institution_identifiers__generate_report__identifier_snapshots_created() -> (
    None
):
    author_institution = create_institution_with_identifiers(
        name="Department of Chemistry",
        ror="https://ror.org/author123",
        isni="https://isni.org/isni/0000000121032683",
    )

    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(
        publication=fr.publication,
        name="John Doe",
        email="john@example.com",
        affiliation=author_institution,
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None
    identifier_snapshots = report_publication.institution_identifiers.all()
    assert identifier_snapshots.count() == 2
    assert identifier_snapshots.filter(
        identifier_type="ror", value="https://ror.org/author123"
    ).exists()
    assert identifier_snapshots.filter(
        identifier_type="isni", value="https://isni.org/isni/0000000121032683"
    ).exists()


@pytest.mark.django_db
def test__publication_with_duplicate_corresponding_authors__generate_report__uses_institution_of_lowest_id_author() -> (
    None
):
    first_institution = create_institution_with_identifiers(
        name="First Author Department",
        ror="https://ror.org/firstauthor",
    )
    second_institution = create_institution_with_identifiers(
        name="Second Author Department",
        ror="https://ror.org/secondauthor",
    )

    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.publication.relevant_authors.all().delete()
    first_author = create_corresponding_author(
        publication=fr.publication,
        name="First Author",
        email="first@example.com",
        affiliation=first_institution,
    )
    second_author = create_corresponding_author(
        publication=fr.publication,
        name="Second Author",
        email="second@example.com",
        affiliation=second_institution,
    )
    low_id_author = min((first_author, second_author), key=lambda author: author.pk)
    if low_id_author.pk == first_author.pk:
        expected_ror, other_ror = "https://ror.org/firstauthor", "https://ror.org/secondauthor"
    else:
        expected_ror, other_ror = "https://ror.org/secondauthor", "https://ror.org/firstauthor"

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None
    assert low_id_author.affiliation is not None
    assert report_publication.institution_name == low_id_author.affiliation.name
    identifiers = report_publication.institution_identifiers
    assert identifiers.filter(identifier_type="ror", value=expected_ror).exists()
    assert not identifiers.filter(identifier_type="ror", value=other_ror).exists()


@pytest.mark.django_db
def test__publication_with_corresponding_author_no_institution_identifiers__generate_report__uses_global_preference_identifiers() -> (
    None
):
    author_institution = Institution.objects.create(name="Department Without Identifiers")

    home_institution = create_institution_with_identifiers(
        name="Home Institution",
        ror="https://ror.org/home456",
    )

    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(
        publication=fr.publication,
        name="John Doe",
        email="john@example.com",
        affiliation=author_institution,
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None
    identifier_snapshots = report_publication.institution_identifiers.all()
    assert identifier_snapshots.count() == 1
    assert identifier_snapshots.filter(
        identifier_type="ror", value="https://ror.org/home456"
    ).exists()


@pytest.mark.django_db
def test__publication_with_author_with_different_institution_identifiers__generate_report__only_ror_isni_ringold_identifier_snapshots_created() -> (
    None
):
    author_institution = create_institution_with_identifiers(
        name="Department of Various Identifiers",
        ror="https://ror.org/various123",
        isni="https://isni.org/isni/0000000121032684",
        ringold="https://ringold.com/id/987654",
    )

    # Add an "other" type identifier that should not be included
    other_type, _ = InstitutionLinkType.objects.get_or_create(name="OtherID")
    InstitutionLink.objects.create(
        institution=author_institution, type=other_type, value="https://otherid.com/id/555555"
    )

    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(
        publication=fr.publication,
        name="Jane Smith",
        email="jane.smith@example.com",
        affiliation=author_institution,
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-002",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None
    identifier_snapshots = report_publication.institution_identifiers.all()
    assert identifier_snapshots.count() == 3
    assert identifier_snapshots.filter(
        identifier_type="ror", value="https://ror.org/various123"
    ).exists()
    assert identifier_snapshots.filter(
        identifier_type="isni", value="https://isni.org/isni/0000000121032684"
    ).exists()
    assert identifier_snapshots.filter(
        identifier_type="ringold", value="https://ringold.com/id/987654"
    ).exists()
    assert not identifier_snapshots.filter(
        identifier_type="otherid", value="https://otherid.com/id/555555"
    ).exists()


@pytest.mark.django_db
def test__publication_with_author_from_child_institution_without_identifiers__generate_report__walks_up_to_parent_institution() -> (
    None
):
    university = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/university123",
    )

    faculty = create_institution_with_identifiers(
        name="Faculty of Science",
        ror="https://ror.org/faculty123",
        parent=university,
    )

    department = Institution.objects.create(name="Department of Physics", parent=faculty)

    fr = modelfactory.fundingrequest(title="Test Publication from Department")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(
        publication=fr.publication,
        name="Dr. Smith",
        email="smith@physics.example.com",
        affiliation=department,
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-HIERARCHY-001",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None

    assert report_publication.institution_name == "Faculty of Science"
    identifier_snapshots = report_publication.institution_identifiers.all()
    assert identifier_snapshots.filter(
        identifier_type="ror", value="https://ror.org/faculty123"
    ).exists()


@pytest.mark.django_db
def test__standalone_contract_with_invoice_positions__generate_report__contract_data_is_snapshotted() -> (
    None
):
    contract = modelfactory.contract()

    creditor = create_creditor(name="Contract Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-CONTRACT-001"
    )

    create_position(
        invoice=invoice,
        contract=contract,
        contract_year=2024,
        description="Read access fee",
        cost_amount=Decimal("5000.00"),
        cost_type="read",
    )
    create_position(
        invoice=invoice,
        contract=contract,
        contract_year=2024,
        description="Publish fee",
        cost_amount=Decimal("3000.00"),
        cost_type="publish",
    )

    report = create_opencost_report(title="Test Report with Contract Data 2024")

    report_contracts = OpenCostReportContract.objects.filter(report=report)
    assert report_contracts.count() == 1

    report_contract = report_contracts.first()
    assert report_contract is not None
    assert report_contract.contract == contract
    assert report_contract.contract_name == contract.name
    assert report_contract.participation_from == contract.start_date
    assert report_contract.participation_to == contract.end_date

    contract_invoices = OpenCostReportContractInvoice.objects.filter(
        report_contract=report_contract
    )

    contract_invoice = contract_invoices.first()
    assert contract_invoice is not None
    assert contract_invoice.invoice == invoice
    assert contract_invoice.invoice_number == "INV-CONTRACT-001"
    assert contract_invoice.creditor == "Contract Creditor"
    assert contract_invoice.amount_invoice == Decimal("8000.00")  # 5000 + 3000
    assert contract_invoice.amount_invoice_currency == "EUR"

    contract_positions = contract_invoice.positions.all()
    assert contract_positions.count() == 2

    amounts = {pos.amount for pos in contract_positions}
    assert Decimal("5000.00") in amounts
    assert Decimal("3000.00") in amounts

    cost_types = {pos.cost_type for pos in contract_positions}
    assert "read" in cost_types
    assert "publish" in cost_types


@pytest.mark.django_db
def test__contract_with_esac_id__generate_report__primary_identifier_snapshotted() -> None:
    contract = create_contract_with_identifiers(
        esac="https://esac.org/id/123456",
    )

    creditor = create_creditor(name="Test Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-001", status="paid"
    )
    create_position(
        invoice=invoice,
        contract=contract,
        cost_amount=Decimal("1000.00"),
        cost_type="publish",
    )

    report = create_opencost_report(title="Test Report with Contract ESAC ID 2024")

    report_contracts = OpenCostReportContract.objects.filter(report=report)
    assert report_contracts.count() == 1

    report_contract = report_contracts.first()
    assert report_contract is not None

    assert report_contract.primary_identifier_value == "https://esac.org/id/123456"


@pytest.mark.django_db
def test__contract_with_secondary_ids__generate_report__secondary_identifier_snapshots_created() -> (
    None
):
    contract = create_contract_with_identifiers(
        oai="https://services.dnb.de/oai/repository/789012",
        ezb="https://ezb.uni-regensburg.de/id/456789",
        local="LOCAL-ID-001",
    )

    creditor = create_creditor(name="Test Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-002", status="paid"
    )
    create_position(
        invoice=invoice,
        contract=contract,
        cost_amount=Decimal("2000.00"),
        cost_type="read",
    )

    report = create_opencost_report(title="Test Report with Contract Secondary IDs 2024")

    report_contracts = OpenCostReportContract.objects.filter(report=report)
    assert report_contracts.count() == 1

    report_contract = report_contracts.first()
    assert report_contract is not None

    identifier_snapshots = report_contract.secondary_identifiers.all()

    assert identifier_snapshots.filter(
        identifier_type="oai", value="https://services.dnb.de/oai/repository/789012"
    ).exists()

    assert identifier_snapshots.filter(
        identifier_type="ezb", value="https://ezb.uni-regensburg.de/id/456789"
    ).exists()

    assert identifier_snapshots.filter(identifier_type="local", value="LOCAL-ID-001").exists()


@pytest.mark.django_db
def test__publication_linked_to_contract__generate_report__publication_and_contract_snapshots_created() -> (
    None
):
    contract = modelfactory.contract()

    creditor = create_creditor(name="Contract Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-CONTRACT-003"
    )

    create_position(
        invoice=invoice,
        contract=contract,
        contract_year=2024,
        description="Publish fee",
        cost_amount=Decimal("4000.00"),
        cost_type="publish",
    )

    fr = modelfactory.fundingrequest(title="Publication Linked to Contract")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-PUB-001",
        creditor_name="Publication Creditor",
        cost_amount=Decimal("1500.00"),
        cost_type="APC",
    )

    AttachedContract.objects.create(
        contract=contract,
        publication=fr.publication,
        contract_year=2024,
    )

    report = create_opencost_report(title="Test Report with Publication and Contract 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr.publication
    ).exists()
    assert OpenCostReportContract.objects.filter(report=report, contract=contract).exists()

    report_publication = report.publications.first()
    assert report_publication is not None
    assert report_publication.linked_contracts.filter(contract=contract).exists()


@pytest.mark.django_db
def test__publication_linked_to_contract__generate_report__publication_has_link_to_contract() -> (
    None
):
    contract = create_contract_with_identifiers(
        esac="https://esac.org/id/654321",
    )

    creditor = create_creditor(name="Contract Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 10), number="INV-CONTRACT-004"
    )

    create_position(
        invoice=invoice,
        contract=contract,
        contract_year=2024,
        description="Read access fee",
        cost_amount=Decimal("6000.00"),
        cost_type="read",
    )

    fr = modelfactory.fundingrequest(title="Publication Linked to Contract with ESAC ID")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-PUB-002",
        creditor_name="Publication Creditor",
        cost_amount=Decimal("1800.00"),
        cost_type="gold-oa",
    )

    AttachedContract.objects.create(
        contract=contract,
        publication=fr.publication,
        contract_year=2024,
    )

    report = create_opencost_report(title="Test Report with Publication and Contract ESAC ID 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr.publication
    ).exists()
    assert OpenCostReportContract.objects.filter(report=report, contract=contract).exists()

    report_publication = report.publications.first()
    assert report_publication is not None
    assert report_publication.linked_contracts.filter(contract=contract).exists()

    linked_contract = report_publication.linked_contracts.first()
    assert linked_contract is not None
    assert linked_contract.contract == contract
    assert linked_contract.contract_year == 2024

    assert linked_contract.group_id is not None
    assert linked_contract.group_id != ""
    assert len(linked_contract.group_id) == 36

    report_contract = report.contracts.filter(contract=contract).first()
    assert report_contract is not None
    contract_invoice = report_contract.invoices.first()
    assert contract_invoice is not None
    assert contract_invoice.group_id == linked_contract.group_id


@pytest.mark.django_db
def test__publication_linked_to_contract_with_no_own_invoice_positions__generate_report__publication_is_included() -> (
    None
):
    contract = create_contract_with_identifiers(
        esac="https://esac.org/id/777777",
    )

    creditor = create_creditor(name="Contract Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 5, 15), number="INV-CONTRACT-005"
    )
    create_position(
        invoice=invoice,
        contract=contract,
        contract_year=2024,
        description="Transformative agreement fee",
        cost_amount=Decimal("10000.00"),
        cost_type="read",
    )

    fr = modelfactory.fundingrequest(
        title="Publication Fully Covered by Contract - No Individual Invoice Positions"
    )
    AttachedContract.objects.create(
        contract=contract,
        publication=fr.publication,
        contract_year=2024,
    )

    report = create_opencost_report(title="Test Report with Publication Covered by Contract 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr.publication
    ).exists()

    assert OpenCostReportContract.objects.filter(report=report, contract=contract).exists()

    report_publication = report.publications.filter(publication=fr.publication).first()
    assert report_publication is not None
    assert report_publication.linked_contracts.filter(contract=contract).exists()

    assert report_publication.invoices.count() == 0

    linked_contract = report_publication.linked_contracts.first()
    assert linked_contract is not None
    assert linked_contract.group_id is not None
    assert linked_contract.group_id != ""

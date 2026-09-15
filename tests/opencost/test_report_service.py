"""What a report is made of, and what generation records about it.

Generation decides which publications, contracts and invoices a report covers, keeps one row per
item it considered, and stores the openCost document the items add up to. These tests hold those
three things to each other: which items the report takes, what each of its rows says about the
item behind it, and what the stored document states about the item's own live records.
"""

from datetime import date
from decimal import Decimal

import pytest
from pytest_django.fixtures import DjangoAssertNumQueries

from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportInvoice,
    OpenCostReportPublication,
)
from coda.apps.opencost.report_service import generate_report
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models._attachedentities import (
    AttachedContract,
)
from coda.apps.publications.models._links import Link, LinkType
from opencost import ContractType, InstitutionType, PublicationType
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
    create_corresponding_author,
    create_creditor,
    create_institution_with_identifiers,
    create_invoice,
    create_opencost_report,
    create_position,
    create_publication_with_invoice,
    stored_document,
)

PERIOD_START = date(2024, 1, 1)
PERIOD_END = date(2024, 12, 31)


def _publication_report(title: str = "Report") -> OpenCostReport:
    return create_opencost_report(title=title, period_start=PERIOD_START, period_end=PERIOD_END)


def _document_publication(report: OpenCostReport) -> PublicationType:
    """The one publication the report exports."""
    publications = stored_document(report).publication or []
    assert len(publications) == 1
    return publications[0]


def _document_contract(report: OpenCostReport) -> ContractType:
    """The one contract the report exports."""
    contracts = stored_document(report).contract or []
    assert len(contracts) == 1
    return contracts[0]


def _institution_identifiers(institution: InstitutionType) -> set[tuple[str, str]]:
    return {(identifier.type.value, identifier.value) for identifier in institution.id or []}


def _institution_name(institution: InstitutionType) -> str:
    names = [name.value for name in institution.name or []]
    assert len(names) == 1
    return names[0]


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
    """The filters are kept with the report, so the report can be run again the same way."""
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
def test__publication_with_a_journal__generate_report__row_keeps_what_the_document_states_elsewhere() -> (
    None
):
    """The row names its publication and keeps the two values openCost has no place for.

    Everything else the document states — the DOI, the publisher, the amounts — is read from the
    publication and its invoices as the document is written, so only the title and the publisher
    survive as columns: the detail page needs them for a row that exports nothing.
    """
    fr = modelfactory.fundingrequest(title="Test Publication")
    assert fr.publication.article_journal is not None
    journal = fr.publication.article_journal
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
        creditor_name="Test Creditor",
    )

    report = _publication_report(title="Test Report with Publication 2024")

    row = OpenCostReportPublication.objects.get(report=report)
    assert row.publication == fr.publication
    assert row.title == "Test Publication"
    assert row.publisher == journal.publisher.name
    assert (row.exported, row.had_errors) == (True, False)

    entry = _document_publication(report)
    assert entry.primary_identifier.doi == "10.1234/5678"
    assert entry.institution is not None


@pytest.mark.django_db
def test__publication_with_invoice_data__generate_report__links_the_invoice_it_was_invoiced_on() -> (
    None
):
    """One row ties the report's publication to the invoice it holds a position on.

    The invoice's own records are not copied: the number the document carries is read from the
    invoice as the document is written.
    """
    fr = modelfactory.fundingrequest(title="Invoice Test Publication")
    fr.publication.online_publication_date = date(2024, 5, 15)
    fr.publication.save()

    invoice, _ = create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
    )

    report = _publication_report(title="Test Report with Invoice 2024")

    row = OpenCostReportPublication.objects.get(report=report)
    report_invoice = OpenCostReportInvoice.objects.get(report_publication=row)
    assert report_invoice.invoice == invoice
    assert (report_invoice.exported, report_invoice.had_errors) == (True, False)

    invoices = _document_publication(report).cost_data.invoice or []
    assert len(invoices) == 1
    assert invoices[0].invoice_number == "INV-2024-001"
    assert invoices[0].creditor == "Invoice Creditor"


@pytest.mark.django_db
def test__invoice_with_two_positions__generate_report__states_both_amounts_of_that_one_invoice() -> (
    None
):
    """Two positions of one invoice are one invoice: its amounts, taxes and currency of both."""
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

    report = _publication_report(title="Test Report with Invoice Positions 2024")

    row = OpenCostReportPublication.objects.get(report=report)
    assert OpenCostReportInvoice.objects.filter(report_publication=row).count() == 1

    invoices = _document_publication(report).cost_data.invoice or []
    amounts_paid = invoices[0].amounts_paid.amount_paid
    assert [(row.amount, row.vat, row.currency) for row in amounts_paid] == [
        (Decimal("500.00"), Decimal("95.00"), "EUR"),
        (Decimal("1000.00"), Decimal("190.00"), "EUR"),
    ]
    assert [row.cost_type.value for row in amounts_paid] == ["gold-oa", "gold-oa"]
    assert invoices[0].amount_invoice is not None
    assert invoices[0].amount_invoice.amount == Decimal("1500.00")


@pytest.mark.django_db
def test__publication_with_multiple_invoices__generate_report__links_every_invoiced_invoice() -> (
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

    report = _publication_report(title="Test Report with Multiple Invoices 2024")

    row = OpenCostReportPublication.objects.get(report=report)
    assert [link.invoice_id for link in row.invoices.all()] == [invoice1.id, invoice2.id]

    invoices = _document_publication(report).cost_data.invoice or []
    assert [invoice.invoice_number for invoice in invoices] == [
        "INV-2024-101",
        "INV-2024-102",
    ]


@pytest.mark.django_db
def test__publication_with_invoice_outside_period__generate_report__publication_not_included() -> (
    None
):
    """An invoice of another period says nothing about this report's items."""
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
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert not OpenCostReportPublication.objects.filter(
        report=report, publication=fr.publication
    ).exists()


@pytest.mark.django_db
def test__publication_with_invoices_inside_and_outside_period__generate_report__links_only_the_periods_invoices() -> (
    None
):
    """The publication belongs to the report, its out-of-period invoice does not."""
    fr = modelfactory.fundingrequest(title="Publication with Multiple Period Invoices")

    in_period, _ = create_publication_with_invoice(
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

    row = OpenCostReportPublication.objects.get(report=report)
    assert row.publication == fr.publication
    assert [link.invoice_id for link in row.invoices.all()] == [in_period.id, invoice_2.id]

    invoices = _document_publication(report).cost_data.invoice or []
    assert [invoice.invoice_number for invoice in invoices] == ["INV-Q2-001", "INV-Q2-002"]


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

    report = _publication_report(title="Test Report with Multiple Publications 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr1.publication
    ).exists()
    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr2.publication
    ).exists()
    assert len(stored_document(report).publication or []) == 2


@pytest.mark.django_db
def test__publication_with_links__generate_report__the_document_names_the_publications_identifiers() -> (
    None
):
    """The identifiers are the publication's live links, not a copy taken at generation."""
    fr = modelfactory.fundingrequest(title="Publication with Links")
    # The factory gives the publication a DOI and an ISBN; Handle and URN are added here.
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=fr.publication, type=handle_type, value="hdl:1234/original")
    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    Link.objects.create(publication=fr.publication, type=urn_type, value="urn:nbn:de:original")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = _publication_report()

    entry = _document_publication(report)
    assert entry.secondary_identifiers is not None
    values = {identifier.value for identifier in entry.secondary_identifiers.id or []}
    assert {"hdl:1234/original", "urn:nbn:de:original"} <= values
    assert len(values) == 3


@pytest.mark.django_db
def test__publication_with_institution_identifiers__generate_report__the_document_names_the_authors_institution() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(
        publication=fr.publication,
        name="John Doe",
        email="john@example.com",
        affiliation=create_institution_with_identifiers(
            name="Department of Chemistry",
            ror="https://ror.org/author123",
            isni="https://isni.org/isni/0000000121032683",
        ),
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = _publication_report()

    institution = _document_publication(report).institution
    assert _institution_name(institution) == "Department of Chemistry"
    assert _institution_identifiers(institution) == {
        ("ror", "https://ror.org/author123"),
        ("isni", "https://isni.org/isni/0000000121032683"),
    }


@pytest.mark.django_db
def test__publication_with_duplicate_corresponding_authors__generate_report__names_the_institution_of_the_first_author() -> (
    None
):
    """Two corresponding authors, two institutions: the record order decides whose it is."""
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
    expected_ror, other_ror = (
        ("https://ror.org/firstauthor", "https://ror.org/secondauthor")
        if low_id_author.pk == first_author.pk
        else ("https://ror.org/secondauthor", "https://ror.org/firstauthor")
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    report = _publication_report()

    institution = _document_publication(report).institution
    assert low_id_author.affiliation is not None
    assert _institution_name(institution) == low_id_author.affiliation.name
    identifiers = _institution_identifiers(institution)
    assert ("ror", expected_ror) in identifiers
    assert ("ror", other_ror) not in identifiers


@pytest.mark.django_db
def test__publication_with_unidentified_author_institution__generate_report__names_the_home_institution() -> (
    None
):
    """An institution nothing is known about is not worth naming: the home institution is."""
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

    report = _publication_report()

    institution = _document_publication(report).institution
    assert _institution_name(institution) == "Home Institution"
    assert _institution_identifiers(institution) == {("ror", "https://ror.org/home456")}


@pytest.mark.django_db
def test__publication_with_author_of_many_identifiers__generate_report__names_the_knowable_identifier_kinds() -> (
    None
):
    """openCost has no member for an identifier of another kind, so it stays out of the document."""
    author_institution = create_institution_with_identifiers(
        name="Department of Various Identifiers",
        ror="https://ror.org/various123",
        isni="https://isni.org/isni/0000000121032684",
        ringold="https://ringold.com/id/987654",
    )

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

    report = _publication_report()

    assert _institution_identifiers(_document_publication(report).institution) == {
        ("ror", "https://ror.org/various123"),
        ("isni", "https://isni.org/isni/0000000121032684"),
        ("ringold", "https://ringold.com/id/987654"),
    }


@pytest.mark.django_db
def test__publication_with_author_from_child_institution_without_identifiers__generate_report__names_the_parent() -> (
    None
):
    """A department nothing identifies walks up to the first of its ancestors that can be named."""
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

    report = _publication_report()

    institution = _document_publication(report).institution
    assert _institution_name(institution) == "Faculty of Science"
    assert _institution_identifiers(institution) == {("ror", "https://ror.org/faculty123")}


@pytest.mark.django_db
def test__standalone_contract_with_invoice_positions__generate_report__states_the_contracts_own_cost_data() -> (
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

    report = _publication_report(title="Test Report with Contract Data 2024")

    row = OpenCostReportContract.objects.get(report=report)
    assert row.contract == contract
    invoice_row = OpenCostReportContractInvoice.objects.get(report_contract=row)
    assert invoice_row.invoice == invoice

    entry = _document_contract(report)
    assert entry.contract_name == contract.name
    assert contract.start_date is not None and contract.end_date is not None
    assert (entry.participation.from_, entry.participation.to) == (
        contract.start_date.isoformat(),
        contract.end_date.isoformat(),
    )
    invoices = entry.cost_data.invoice_group[0].invoice or []
    assert [invoice.invoice_number for invoice in invoices] == ["INV-CONTRACT-001"]
    amounts_paid = invoices[0].amounts_paid.amount_paid
    assert {(row.cost_type.value, row.amount) for row in amounts_paid} == {
        ("read", Decimal("5000.00")),
        ("publish", Decimal("3000.00")),
    }
    assert invoices[0].amount_invoice is not None
    assert invoices[0].amount_invoice.amount == Decimal("8000.00")
    assert invoices[0].amount_invoice.currency == "EUR"


@pytest.mark.django_db
def test__contract_with_esac_id__generate_report__the_document_names_the_contract_by_it() -> None:
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

    report = _publication_report(title="Test Report with Contract ESAC ID 2024")

    assert OpenCostReportContract.objects.filter(report=report, contract=contract).count() == 1
    entry = _document_contract(report)
    assert entry.primary_identifier.value == "https://esac.org/id/123456"
    assert entry.primary_identifier.type.value == "ESAC"


@pytest.mark.django_db
def test__contract_with_secondary_ids__generate_report__the_document_carries_the_contracts_identifiers() -> (
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

    report = _publication_report(title="Test Report with Contract Secondary IDs 2024")

    entry = _document_contract(report)
    assert entry.secondary_identifiers is not None
    assert {
        (identifier.type.value, identifier.value)
        for identifier in entry.secondary_identifiers.id or []
    } == {
        ("oai", "https://services.dnb.de/oai/repository/789012"),
        ("ezb", "https://ezb.uni-regensburg.de/id/456789"),
        ("local", "LOCAL-ID-001"),
    }


@pytest.mark.django_db
def test__publication_linked_to_contract__generate_report__both_items_get_their_own_row() -> None:
    """The contract is in the report for its own positions, the publication for its own."""
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

    report = _publication_report(title="Test Report with Publication and Contract 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr.publication
    ).exists()
    assert OpenCostReportContract.objects.filter(report=report, contract=contract).exists()


@pytest.mark.django_db
def test__publication_linked_to_contract__generate_report__the_document_links_it_to_the_contracts_invoices() -> (
    None
):
    """``part_of_contract`` carries the group id of the contract's own invoice group."""
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

    report = _publication_report(title="Test Report with Publication and Contract ESAC ID 2024")

    assert OpenCostReportPublication.objects.filter(
        report=report, publication=fr.publication
    ).exists()
    assert OpenCostReportContract.objects.filter(report=report, contract=contract).exists()

    publication = _document_publication(report)
    contract_entry = _document_contract(report)
    part_of_contract = publication.cost_data.part_of_contract
    assert part_of_contract is not None
    assert part_of_contract.primary_identifier.value == "https://esac.org/id/654321"
    assert part_of_contract.group_id == contract_entry.cost_data.invoice_group[0].group_id


@pytest.mark.django_db
def test__publication_linked_to_contract_with_no_own_invoice_positions__generate_report__publication_is_included() -> (
    None
):
    """A publication paid for through a contract is reported by that contract alone.

    It holds no position on any invoice, so it gets no invoice row; the document states its cost
    as the link to the contract that covers it.
    """
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

    report = _publication_report(title="Test Report with Publication Covered by Contract 2024")

    row = OpenCostReportPublication.objects.get(report=report, publication=fr.publication)
    assert OpenCostReportContract.objects.filter(report=report, contract=contract).exists()
    assert row.invoices.count() == 0
    assert (row.exported, row.had_errors) == (True, False)

    publication = _document_publication(report)
    assert publication.cost_data.invoice is None
    assert publication.cost_data.part_of_contract is not None


@pytest.mark.django_db
def test__publication_whose_invoice_is_unusable__generate_report__every_considered_row_is_kept() -> (
    None
):
    """A row stays when its item turns out to be unreportable — that is how the report says so.

    The publication and its invoice are considered, so both get a row; the invoice's amount rows
    carry cost types openCost has no name for, so nothing is exported and both rows are marked as
    having failed. The document holds neither item, and the issue log explains the loss.
    """
    publication = modelfactory.publication(title="Article with an unusable invoice")
    create_publication_with_invoice(
        publication,
        invoice_number="INV-UNUSABLE",
        cost_amount=Decimal("1500.00"),
        cost_type="not-a-cost-type",
    )

    report = _publication_report()

    row = OpenCostReportPublication.objects.get(report=report, publication=publication)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (False, True, None)
    invoice_row = OpenCostReportInvoice.objects.get(report_publication=row)
    assert (invoice_row.exported, invoice_row.had_errors, invoice_row.xml_index) == (
        False,
        True,
        None,
    )
    assert report.xml_content == ""
    assert report.has_issues() is True


@pytest.mark.django_db
def test__clean_report_with_institution_doi_and_esac__generate_report__has_no_issues() -> None:
    """A report whose publication and contract export cleanly reports no issues.

    Home institution with identifiers, publication with DOI and invoice, contract with ESAC,
    participation dates and an invoice: nothing had to be left out or made up.
    """
    home_institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/test123",
    )
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    publication = modelfactory.publication(title="Valid Publication")
    Link.objects.create(
        publication=publication,
        type=doi_type,
        value="10.1234/test.123",
    )
    create_publication_with_invoice(publication)

    contract = create_contract_with_identifiers(
        name="Valid Contract",
        esac="https://esac.org/id/123",
    )
    create_contract_with_invoice(contract)

    report = generate_report(
        title="Clean Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    assert report.has_issues() is False
    assert report.get_issue_counts() == {"errors": 0, "warnings": 0}


@pytest.mark.django_db
def test__missing_doi_esac_and_participation_dates__generate_report__counts_separate_errors_and_warnings() -> (
    None
):
    """Substitutions warn (DOI, ESAC); exclusions error (no participation dates)."""
    home_institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/test123",
    )
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    # 3 publications without DOI: exported with BibliographicInformation instead (warnings)
    for i in range(3):
        fr = modelfactory.fundingrequest(title=f"Publication Without DOI {i}")
        fr.publication.links.filter(type__name="DOI").delete()
        create_publication_with_invoice(
            fr.publication,
            invoice_date=date(2024, 6, 15),
            invoice_number=f"INV-PUB-{i}",
            cost_amount=Decimal("1500.00"),
        )

    # 2 contracts without ESAC: exported with ESAC 'UNKNOWN' instead (warnings)
    for i in range(2):
        contract = create_contract_with_identifiers(
            name=f"Contract Without ESAC {i}",
        )
        create_contract_with_invoice(
            contract,
            invoice_date=date(2024, 6, 1),
            invoice_number=f"INV-CONTRACT-{i}",
        )

    # 1 contract without participation dates: excluded entirely (error)
    contract = modelfactory.contract()
    contract.name = "Undated Agreement"
    contract.start_date = None
    contract.end_date = None
    contract.save()
    create_contract_with_invoice(contract, invoice_number="INV-UNDATED")

    report = generate_report(
        title="Mixed Issues Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    issues = report.issues
    doi_warnings = [w for w in issues if "DOI" in w["message"] and w["level"] == "warning"]
    esac_warnings = [w for w in issues if "ESAC" in w["message"] and w["level"] == "warning"]
    participation_errors = [
        w for w in issues if "participation" in w["message"] and w["level"] == "error"
    ]
    assert len(doi_warnings) >= 3
    assert len(esac_warnings) >= 2
    assert len(participation_errors) >= 1

    counts = report.get_issue_counts()
    assert counts["warnings"] >= 5
    assert counts["errors"] >= 1
    assert report.has_issues() is True


@pytest.mark.django_db
def test__two_publications__generate_report__query_count_stays_bounded(
    django_assert_max_num_queries: DjangoAssertNumQueries,
) -> None:
    """Guard the end-to-end query count without the performance marker.

    Deliberately unmarked so it also runs under ``pdm run unittests``, which filters
    performance-marked tests out. Two publications with invoices exercise the full path: the
    item selection, the one invoice fetch, the seed rows and the pass that writes the stored
    document from them. Measured 28 queries for this fixture (2 publications with invoices,
    home institution, no contracts), against the 50 the snapshot pipeline needed for the same
    data; pinned at 35 to leave headroom for prefetch additions.
    """
    home_institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/test123",
    )
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    for i in range(2):
        fr = modelfactory.fundingrequest(title=f"Query Guard Publication {i}")
        create_publication_with_invoice(
            fr.publication,
            invoice_date=date(2024, 6, 15),
            invoice_number=f"INV-QUERY-{i:03d}",
        )

    with django_assert_max_num_queries(35):
        generate_report(
            title="Query Guard Report",
            filters={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
        )

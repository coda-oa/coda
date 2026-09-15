"""Generation's dual write: the stored document against the snapshot document.

The report pages read the snapshot tables, and downloading a report turns those into openCost.
Generation now also stores the document, built from the same live data by a second transform, so
that the artifact and the row outcomes next to it are there before anyone asks for a download.
These tests hold the two to each other: for every shape of data a report can be made from, the
stored document must *be* the document the snapshot produces, and the outcomes written next to it
must say how each of its pieces got there.

Comparison smooths only what a second transform is allowed to differ in: the group ids it invents
for this run, the precision the writer already fixes at two decimals, and the order of two amount
rows that carry the same amount.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Literal
from xml.etree import ElementTree as ET

import pytest

import opencost
from coda.apps.institutions.models import Institution
from coda.apps.opencost import report_service
from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportInvoice,
    OpenCostReportPublication,
)
from coda.apps.opencost.report_service import generate_report
from coda.apps.opencost.services.queries import load_transform_tree
from coda.apps.opencost.xml_generation import generate_xml
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import Publication
from coda.apps.publications.models._attachedentities import AttachedContract
from coda.apps.publications.models._links import Link, LinkType
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
    create_corresponding_author,
    create_creditor,
    create_institution_with_identifiers,
    create_invoice,
    create_position,
    create_publication_with_invoice,
)

FILTERS = {
    "period_start": date(2024, 1, 1).isoformat(),
    "period_end": date(2024, 12, 31).isoformat(),
}

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_DECIMAL_ELEMENTS = frozenset({"amount", "vat"})
_UNSET = object()


# ---------------------------------------------------------------------------------------------
# Comparing the two documents
# ---------------------------------------------------------------------------------------------


def _stored_document(report: OpenCostReport) -> str:
    """The artifact as stored, read back from the database instead of the generated object."""
    return OpenCostReport.objects.get(pk=report.pk).xml_content


def _snapshot_document(report: OpenCostReport) -> str:
    """What downloading the report produces from its snapshot."""
    publications, contracts = load_transform_tree(report)
    return generate_xml(report, publications, contracts)


def _canonical(document: str) -> str:
    """The document as text, freed of what a second transform may differ in.

    ``group_id`` is a fresh uuid4 per contract per run, so what is compared is which entries share
    a group, not the id. Amounts are compared at the two decimals the XML writer prints anyway.
    And the amount rows of one invoice are put in a fixed order among themselves: positions were
    read in amount order with no tie-breaker, so two rows of equal amount have no order to agree
    on - rows of different amounts still have to come out in the same order.
    """
    if not document:
        return ""

    root = ET.fromstring(document)
    groups: dict[str, str] = {}
    for element in root.iter():
        element.tag = element.tag.rpartition("}")[2]
        if element.tag == "group_id" and element.text and _UUID.fullmatch(element.text):
            element.text = groups.setdefault(element.text, f"group-{len(groups) + 1}")
        elif element.tag in _DECIMAL_ELEMENTS and element.text:
            element.text = f"{Decimal(element.text):.2f}"

    for element in root.iter():
        if element.tag == "amounts_paid":
            element[:] = sorted(element, key=_amount_row_order)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def _amount_row_order(row: ET.Element) -> tuple[str, str]:
    amount = row.findtext("amount") or ""
    signature = "|".join(f"{child.tag}={child.text}" for child in row)
    return amount, signature


# ---------------------------------------------------------------------------------------------
# Fixtures


def _home_institution(configure: bool = True) -> Institution:
    """The home institution a report falls back to, with all three identifier types."""
    prefs, _ = GlobalPreferences.objects.get_or_create()
    if configure and prefs.home_institution is not None:
        return prefs.home_institution

    institution = create_institution_with_identifiers(
        name="Home University",
        ror="https://ror.org/0home",
        isni="1234-isni",
        ringold="ringold-home",
    )
    prefs.home_institution = institution if configure else None
    prefs.save()

    return institution


def _generate(title: str = "Dual write report") -> OpenCostReport:
    return generate_report(title=title, filters=FILTERS)


def _link(publication: Publication, type_name: str, value: str) -> None:
    link_type, _ = LinkType.objects.get_or_create(name=type_name)
    Link.objects.create(publication=publication, type=link_type, value=value)


def _publication(
    title: str,
    *,
    doi: str | None = "10.1000/first",
    extra_links: tuple[str, ...] = (),
    publisher: Literal["journal", "monograph", "none"] = "journal",
    affiliation: Institution | None = _UNSET,  # type: ignore[assignment]
    costsplitting: bool | None = None,
) -> Publication:
    """A publication with exactly the CODA records the report reads off it.

    It comes with the funding request it was filed under, since an issue found on a publication
    is offered up as a link to that request.
    """
    request = modelfactory.fundingrequest(title=title)
    publication = request.publication
    assert publication is not None
    publication.links.all().delete()
    if publisher != "journal":
        publication.article_journal = None
        if publisher == "monograph":
            publication.monograph_publisher = modelfactory.publisher(name="Monograph Press")
    if costsplitting is not None:
        request.external_costsplitting = costsplitting
        request.save()
    publication.save()

    if doi:
        _link(publication, "DOI", doi)
    for name in extra_links:
        _link(publication, name, f"{name.lower()}-one")

    if affiliation is _UNSET:
        affiliation = _home_institution()
    if affiliation is not None:
        create_corresponding_author(publication, affiliation=affiliation)

    return publication


def _clean_publication() -> None:
    publication = _publication(
        "Clean article",
        extra_links=("Handle", "URN"),
        costsplitting=True,
    )
    create_publication_with_invoice(
        publication,
        invoice_number="INV-CLEAN",
        creditor_name="Invoice Creditor",
        cost_amount=Decimal("1500.00"),
    )


def _doi_less_publication() -> None:
    publication = _publication("DOI-less article", doi=None)
    create_publication_with_invoice(publication, invoice_number="INV-NODOI")


def _institution_less_publication() -> None:
    """No home institution and no affiliated author: the institution cannot be named at all."""
    _home_institution(configure=False)
    publication = _publication("Orphan article", affiliation=None)
    create_publication_with_invoice(publication, invoice_number="INV-ORPHAN")


def _parent_institution_publication() -> None:
    """The author's institution carries no identifiers; its parent's are what gets read."""
    parent = create_institution_with_identifiers(name="Parent University", ror="https://ror.org/p")
    child = create_institution_with_identifiers(name="Child Department", parent=parent)
    publication = _publication("Affiliated article", affiliation=child)
    create_publication_with_invoice(publication, invoice_number="INV-PARENT")


def _monograph_publication() -> None:
    """No journal to take a title from: the monograph publisher is the fallback."""
    publication = _publication("Bound monograph", doi=None, publisher="monograph")
    create_publication_with_invoice(publication, invoice_number="INV-MONOGRAPH")


def _publisher_less_publication() -> None:
    """Neither a journal nor a publisher anywhere: the export has to say it does not know."""
    publication = _publication("Unpublished article", doi=None, publisher="none")
    create_publication_with_invoice(publication, invoice_number="INV-NOPUB")


def _two_invoices_one_publication() -> None:
    publication = _publication("Twice invoiced article")
    create_publication_with_invoice(publication, invoice_number="INV-TWO-A")
    second = create_invoice(
        creditor=create_creditor("Second Creditor"),
        invoice_date=date(2024, 7, 15),
        number="INV-TWO-B",
    )
    create_position(
        second,
        publication,
        cost_amount=Decimal("700.00"),
        cost_currency="GBP",
        cost_type="hybrid-oa",
        tax_rate=Decimal("0.07"),
    )


def _unnumbered_invoice() -> None:
    """A blank invoice number: the element is absent, and issues have to name it anyway."""
    publication = _publication("Untraceable article")
    invoice = create_invoice(creditor=create_creditor(), invoice_date=date(2024, 6, 1), number="")
    create_position(invoice, publication, cost_amount=Decimal("500.00"))


def _unusable_invoice() -> None:
    """Every amount row of the invoice carries a cost type openCost has no name for."""
    publication = _publication("Article with an unusable invoice")
    create_publication_with_invoice(
        publication,
        invoice_number="INV-UNUSABLE",
        cost_amount=Decimal("1500.00"),
        cost_type="not-a-cost-type",
    )


def _partly_unusable_invoice() -> None:
    """One of the two amount rows of the invoice is unusable, so the invoice is exported partly."""
    publication = _publication("Article with one rejected amount row")
    invoice = create_invoice(
        creditor=create_creditor("Invoice Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-PARTLY",
    )
    create_position(invoice, publication, cost_amount=Decimal("1500.00"))
    create_position(
        invoice, publication, cost_amount=Decimal("300.00"), cost_type="not-a-cost-type"
    )


def _equal_amount_positions() -> None:
    """Two positions of the same amount: they have no order to agree on, and must not be swapped
    with a third of a different amount."""
    publication = _publication("Article with two equal rows")
    invoice = create_invoice(
        creditor=create_creditor("Invoice Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-EQUAL",
    )
    create_position(invoice, publication, cost_amount=Decimal("900.00"), cost_type="gold-oa")
    create_position(invoice, publication, cost_amount=Decimal("900.00"), cost_type="other")
    create_position(invoice, publication, cost_amount=Decimal("100.00"), cost_type="other")


def _esac_less_contract() -> None:
    contract = create_contract_with_identifiers(name="No ESAC Agreement")
    create_contract_with_invoice(contract, cost_type="read")


def _contract_with_everything() -> None:
    contract = create_contract_with_identifiers(
        name="Full Agreement", esac="ESAC-FULL", oai="oai:full", ezb="ezb:full", local="local:full"
    )
    create_contract_with_invoice(
        contract,
        position_amounts=[Decimal("1200.00"), Decimal("800.00")],
        cost_type="read",
    )


def _contract_without_participation() -> None:
    contract = create_contract_with_identifiers(name="Undated Agreement", esac="ESAC-UNDATED")
    contract.start_date = None
    contract.end_date = None
    contract.save()
    create_contract_with_invoice(contract)


def _publication_part_of_contract() -> None:
    """The invoice of the contract and the part_of_contract of the publication share one group."""
    contract = create_contract_with_identifiers(name="Linked Agreement", esac="ESAC-LINKED")
    create_contract_with_invoice(contract, invoice_number="INV-CONTRACT-SIDE")
    publication = _publication("Subscribed article")
    create_publication_with_invoice(publication, invoice_number="INV-PUBLICATION-SIDE")
    AttachedContract.objects.create(contract=contract, publication=publication, contract_year=2024)


def _earliest_of_two_contracts() -> None:
    """Two contracts cover the publication; the earliest participation year names it."""
    older = create_contract_with_identifiers(name="Older Agreement", esac="ESAC-OLDER")
    newer = create_contract_with_identifiers(name="Newer Agreement", esac="ESAC-NEWER")
    create_contract_with_invoice(newer)
    publication = _publication("Long subscribed article")
    create_publication_with_invoice(publication, invoice_number="INV-ELDER")
    AttachedContract.objects.create(contract=newer, publication=publication, contract_year=2024)
    AttachedContract.objects.create(contract=older, publication=publication, contract_year=2023)


def _attachment_without_cost() -> None:
    """The earliest attachment carries no in-period cost, so it is named without a group id."""
    unbilled = create_contract_with_identifiers(name="Unbilled Agreement", esac="ESAC-UNBILLED")
    billed = create_contract_with_identifiers(name="Billed Agreement", esac="ESAC-BILLED")
    create_contract_with_invoice(billed)
    publication = _publication("Mostly unbilled article")
    create_publication_with_invoice(publication, invoice_number="INV-UNBILLED")
    AttachedContract.objects.create(contract=unbilled, publication=publication, contract_year=2023)
    AttachedContract.objects.create(contract=billed, publication=publication, contract_year=2024)
    assert unbilled.position_set.count() == 0


def _same_year_attachment_without_cost() -> None:
    """Two contracts cover the same year: the tie is broken by the attachment itself.

    The snapshot this has to match was read in contract-year order with no rule of its own for a
    tie, so this is where the two ways of reading the same data could part.
    """
    unbilled = create_contract_with_identifiers(name="Unbilled Same Year", esac="ESAC-UNTIED")
    billed = create_contract_with_identifiers(name="Billed Same Year", esac="ESAC-BILLED")
    create_contract_with_invoice(billed, invoice_number="INV-SAME-YEAR-BILLED")
    publication = _publication("Doubly covered article")
    create_publication_with_invoice(publication, invoice_number="INV-TIED-FIRST")
    AttachedContract.objects.create(contract=unbilled, publication=publication, contract_year=2024)
    AttachedContract.objects.create(contract=billed, publication=publication, contract_year=2024)


def _same_year_attachment_with_cost() -> None:
    """The same tie the other way round, the invoiced contract attached first."""
    billed = create_contract_with_identifiers(name="Billed First", esac="ESAC-FIRST")
    unbilled = create_contract_with_identifiers(name="Unbilled Second", esac="ESAC-SECOND")
    create_contract_with_invoice(billed, invoice_number="INV-BILLED-FIRST")
    publication = _publication("Doubly covered article again")
    create_publication_with_invoice(publication, invoice_number="INV-TIED-SECOND")
    AttachedContract.objects.create(contract=billed, publication=publication, contract_year=2024)
    AttachedContract.objects.create(contract=unbilled, publication=publication, contract_year=2024)


def _everything_together() -> None:
    _clean_publication()
    _doi_less_publication()
    _publisher_less_publication()
    _partly_unusable_invoice()
    _equal_amount_positions()
    _two_invoices_one_publication()
    _unnumbered_invoice()
    _contract_with_everything()
    _esac_less_contract()
    _publication_part_of_contract()
    _earliest_of_two_contracts()
    _attachment_without_cost()


SCENARIOS: list[Callable[[], None]] = [
    _clean_publication,
    _doi_less_publication,
    _monograph_publication,
    _publisher_less_publication,
    _institution_less_publication,
    _parent_institution_publication,
    _two_invoices_one_publication,
    _unnumbered_invoice,
    _unusable_invoice,
    _partly_unusable_invoice,
    _equal_amount_positions,
    _esac_less_contract,
    _contract_with_everything,
    _contract_without_participation,
    _publication_part_of_contract,
    _earliest_of_two_contracts,
    _attachment_without_cost,
    _same_year_attachment_without_cost,
    _same_year_attachment_with_cost,
    _everything_together,
]


# ---------------------------------------------------------------------------------------------
# The stored document against the snapshot document
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("build", SCENARIOS, ids=lambda build: build.__name__)
@pytest.mark.django_db
def test_stored_document_is_the_snapshot_document(build: Callable[[], None]) -> None:
    """No shape of data may be exported differently by the transform that stores it."""
    _home_institution()
    build()

    report = _generate()

    stored = _canonical(_stored_document(report))
    snapshot = _canonical(_snapshot_document(report))
    assert stored == snapshot


@pytest.mark.parametrize("build", SCENARIOS, ids=lambda build: build.__name__)
@pytest.mark.django_db
def test_stored_issue_log_costs_the_report_what_a_fresh_check_costs(
    build: Callable[[], None],
) -> None:
    """The stored log is readable issue by issue and agrees with the counts shown next to it."""
    _home_institution()
    build()

    report = _generate()

    stored = [ValidationWarning(**issue) for issue in report.issues]
    assert [asdict(warning) for warning in stored] == report.issues

    counts = report.get_issue_counts()
    assert counts == {
        "errors": sum(1 for warning in stored if warning.level == "error"),
        "warnings": sum(1 for warning in stored if warning.level == "warning"),
    }
    assert counts == {"errors": report.errors_count, "warnings": report.warnings_count}


@pytest.mark.django_db
def test_an_artifact_that_cannot_be_written_leaves_the_report_generated(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The pass that stores the document is allowed to fail; the report it ran for is not."""

    _clean_publication()

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the artifact cannot be built today")

    monkeypatch.setattr(report_service, "transform_report", broken)

    with caplog.at_level(logging.ERROR):
        report = _generate()

    assert "openCost artifact could not be stored" in caplog.text
    assert "the artifact cannot be built today" in caplog.text

    stored = OpenCostReport.objects.get(pk=report.pk)
    assert (stored.xml_content, stored.issues) == ("", [])
    # The counts the page shows come from the pass that did run.
    assert stored.get_issue_counts() == {"errors": 0, "warnings": 0}
    # The snapshot the pages read is whole, and still transforms on demand.
    assert OpenCostReportPublication.objects.filter(report=report).count() == 1
    assert _snapshot_document(report) != ""
    row = OpenCostReportPublication.objects.get(report=report)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (False, False, None)


# ---------------------------------------------------------------------------------------------
# How every row of the report fared
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_clean_export_records_a_row_of_the_document() -> None:
    _clean_publication()

    report = _generate()

    publication = OpenCostReportPublication.objects.get(report=report)
    assert (publication.exported, publication.had_errors, publication.xml_ordinal) == (
        True,
        False,
        0,
    )
    invoice = OpenCostReportInvoice.objects.get(report_publication=publication)
    assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (True, False, 0)


@pytest.mark.parametrize(
    "build, exported",
    [(_doi_less_publication, True), (_publisher_less_publication, True)],
    ids=["doi_less", "publisher_less"],
)
@pytest.mark.django_db
def test_substituted_value_warns_without_marking_the_row_failed(
    build: Callable[[], None], exported: bool
) -> None:
    """A warning writes the document entry it describes and leaves the row otherwise clean."""
    _home_institution()
    build()

    report = _generate()

    row = OpenCostReportPublication.objects.get(report=report)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (exported, False, 0)
    assert {issue["level"] for issue in report.issues} == {"warning"}


@pytest.mark.django_db
def test_partly_unusable_invoice_is_exported_and_marks_its_rows_failed() -> None:
    """The invoice keeps its place with the amount rows openCost could take; the dropped row is
    an error, and it is an error for the publication that lost it too."""
    _partly_unusable_invoice()

    report = _generate()

    row = OpenCostReportPublication.objects.get(report=report)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (True, True, 0)
    invoice = OpenCostReportInvoice.objects.get(report_publication=row)
    assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (True, True, 0)
    assert [issue["level"] for issue in report.issues] == ["error"]


@pytest.mark.django_db
def test_publication_kept_by_its_contract_reports_the_invoice_it_lost() -> None:
    """The publication reaches the document through its contract alone, degraded by the loss."""
    contract = create_contract_with_identifiers(name="Rescue Agreement", esac="ESAC-RESCUE")
    create_contract_with_invoice(contract)
    publication = _publication("Article with a lost invoice")
    create_publication_with_invoice(
        publication,
        invoice_number="INV-LOST",
        cost_amount=Decimal("1500.00"),
        cost_type="not-a-cost-type",
    )
    AttachedContract.objects.create(contract=contract, publication=publication, contract_year=2024)

    report = _generate()

    row = OpenCostReportPublication.objects.get(report=report, publication=publication)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (True, True, 0)
    invoice = OpenCostReportInvoice.objects.get(report_publication=row)
    assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (False, True, None)


@pytest.mark.django_db
def test_excluded_item_keeps_no_place_in_the_document() -> None:
    """What never reached the document says so, and holds no ordinal to point at."""
    _unusable_invoice()

    report = _generate()

    assert _stored_document(report) == ""
    row = OpenCostReportPublication.objects.get(report=report)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (False, True, None)
    invoice = OpenCostReportInvoice.objects.get(report_publication=row)
    assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (False, True, None)


@pytest.mark.django_db
def test_excluded_contract_keeps_no_place_in_the_document() -> None:
    """An item that gives up before its invoices still leaves word about every one of them."""
    _home_institution()
    _contract_without_participation()

    report = _generate()

    assert _stored_document(report) == ""
    contract = OpenCostReportContract.objects.get(report=report)
    assert (contract.exported, contract.had_errors, contract.xml_ordinal) == (False, True, None)
    invoice = OpenCostReportContractInvoice.objects.get(report_contract=contract)
    assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (False, True, None)


@pytest.mark.django_db
def test_exported_contract_counts_its_invoices_from_the_document() -> None:
    _home_institution()
    _contract_with_everything()

    report = _generate()

    contract = OpenCostReportContract.objects.get(report=report)
    assert (contract.exported, contract.had_errors, contract.xml_ordinal) == (True, False, 0)
    invoice = OpenCostReportContractInvoice.objects.get(report_contract=contract)
    assert (invoice.exported, invoice.had_errors, invoice.xml_index) == (True, False, 0)


@pytest.mark.django_db
def test_row_places_join_onto_the_stored_document() -> None:
    """Every exported row points at the entry of the stored document its own data went into."""
    _everything_together()

    report = _generate()

    data = opencost.from_xml(report.xml_content)
    assert data.publication is not None
    assert data.contract is not None

    publications = list(OpenCostReportPublication.objects.filter(report=report, exported=True))
    assert [row.xml_ordinal for row in publications] == list(range(len(publications)))
    for publication_row in publications:
        entry = data.publication[_place(publication_row.xml_ordinal)]
        assert entry.institution is not None
        assert entry.cost_data is not None

    contracts = list(OpenCostReportContract.objects.filter(report=report, exported=True))
    assert [row.xml_ordinal for row in contracts] == list(range(len(contracts)))
    for contract_row in contracts:
        contract_entry = data.contract[_place(contract_row.xml_ordinal)]
        assert contract_entry.contract_name == contract_row.contract_name

    for invoice_row in OpenCostReportInvoice.objects.filter(report_publication__report=report):
        parent = invoice_row.report_publication
        if not parent.exported:
            assert (invoice_row.exported, invoice_row.xml_index) == (False, None)
            continue
        parent_entry = data.publication[_place(parent.xml_ordinal)]
        assert parent_entry.cost_data is not None
        invoices = parent_entry.cost_data.invoice or []
        assert len(invoices) == parent.invoices.filter(exported=True).count()
        number = invoice_row.invoice_number or None
        if invoice_row.exported:
            assert invoices[_place(invoice_row.xml_index)].invoice_number == number
        else:
            assert number not in [invoice.invoice_number for invoice in invoices]

    # Nothing that stayed out of the document can claim to have been exported cleanly.
    assert not OpenCostReportInvoice.objects.filter(
        report_publication__report=report, exported=False, had_errors=False
    ).exists()
    assert not OpenCostReportContractInvoice.objects.filter(
        report_contract__report=report, exported=False, had_errors=False
    ).exists()


def _place(ordinal: int | None) -> int:
    """The document entry an exported row names; an exported row always names one."""
    assert ordinal is not None, "an exported row holds no place in the document"
    return ordinal

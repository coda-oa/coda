"""The document generation stores, for every shape of data a report can be made from.

The stored document is the report's exportable content, and the row outcomes written beside it say
how each of its pieces got there. These tests hold the two to each other across a corpus of data
shapes: what a report exports must be exactly what its rows claim it exported, down to the place
each entry holds in the document and the group id that ties a publication to its contract.

An item the XSD cannot be given is left out and reported instead, so a scenario may well export
nothing at all — which is a result to check, not a reason to skip the test.
"""

from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Literal

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
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import Publication
from coda.apps.publications.models._attachedentities import AttachedContract
from coda.apps.publications.models._links import Link, LinkType
from opencost import ContractType, Data, PublicationType
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

_UNSET = object()


# ---------------------------------------------------------------------------------------------
# Reading back what generation wrote


def _stored_document(report: OpenCostReport) -> str:
    """The artifact as stored, read back from the database instead of the generated object."""
    return OpenCostReport.objects.get(pk=report.pk).xml_content


def _document(report: OpenCostReport) -> Data | None:
    """The stored document as models, or ``None`` when nothing was exportable."""
    stored = _stored_document(report)
    assert stored == report.xml_content, "the generated object and the row disagree"
    return None if not stored else opencost.from_xml(stored)


type InvoiceRow = OpenCostReportInvoice | OpenCostReportContractInvoice


def _place(ordinal: int | None) -> int:
    """The document entry an exported row names; an exported row always names one."""
    assert ordinal is not None, "an exported row holds no place in the document"
    return ordinal


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


def _generate(title: str = "Generated report") -> OpenCostReport:
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
    """Two positions of the same amount: their order is fixed by the fetch, not by chance."""
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

    Nothing below the year orders the two, so this is the shape that pins which one wins — the
    attachment made first, here the one that carries no cost and so no group id.
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

# The scenarios whose publications name a contract, and whether that contract is in the document
# with invoices of its own — which is what a group id on the link means.
LINKED_SCENARIOS: list[tuple[Callable[[], None], bool]] = [
    (_publication_part_of_contract, True),
    (_earliest_of_two_contracts, False),
    (_attachment_without_cost, False),
    (_same_year_attachment_without_cost, False),
    (_same_year_attachment_with_cost, True),
    (_everything_together, True),
]


# ---------------------------------------------------------------------------------------------
# The stored document against the rows beside it
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("build", SCENARIOS, ids=lambda build: build.__name__)
@pytest.mark.django_db
def test_stored_document_holds_exactly_the_items_the_rows_call_exported(
    build: Callable[[], None],
) -> None:
    """No row may claim a place the document does not hold, and no entry may go unclaimed.

    The join is positional by design, so the ordinals and indexes the rows carry are the only
    way back from a row to its entry — every exported row has to point at one, in range, and the
    document may hold nothing beyond what the exported rows add up to.
    """
    _home_institution()
    build()

    report = _generate()

    document = _document(report)
    publications = list(OpenCostReportPublication.objects.filter(report=report))
    contracts = list(OpenCostReportContract.objects.filter(report=report))
    exported_publications = [row for row in publications if row.exported]
    exported_contracts = [row for row in contracts if row.exported]

    # Order is the rows' own: the document lists items in the report's row order.
    assert [row.xml_ordinal for row in exported_publications] == list(
        range(len(exported_publications))
    )
    assert [row.xml_ordinal for row in exported_contracts] == list(range(len(exported_contracts)))

    if document is None:
        assert not exported_publications and not exported_contracts
        return

    entries: list[PublicationType | ContractType] = list(
        (document.publication or []) + (document.contract or [])
    )
    assert all(entry.institution is not None for entry in entries)

    assert len(document.publication or []) == len(exported_publications)
    for row in exported_publications:
        entry = (document.publication or [])[_place(row.xml_ordinal)]
        assert isinstance(entry, PublicationType)
        invoices = entry.cost_data.invoice or []
        assert len(invoices) == row.invoices.filter(exported=True).count()
        _assert_invoice_places(list(row.invoices.all()), len(invoices))

    assert len(document.contract or []) == len(exported_contracts)
    for row in exported_contracts:
        entry = (document.contract or [])[_place(row.xml_ordinal)]
        assert isinstance(entry, ContractType)
        assert entry.contract_name == row.contract_name
        groups = entry.cost_data.invoice_group or []
        invoices = groups[0].invoice if groups else []
        assert len(invoices or []) == row.invoices.filter(exported=True).count()
        _assert_invoice_places(list(row.invoices.all()), len(invoices or []))

    # Nothing that stayed out of the document can claim to have been exported cleanly.
    assert not OpenCostReportInvoice.objects.filter(
        report_publication__report=report, exported=False, had_errors=False
    ).exists()
    assert not OpenCostReportContractInvoice.objects.filter(
        report_contract__report=report, exported=False, had_errors=False
    ).exists()


def _assert_invoice_places(rows: Sequence[InvoiceRow], number_of_exported_invoices: int) -> None:
    """Every invoice row says where it stands, and only an exported one stands anywhere."""
    exported = [row for row in rows if row.exported]
    assert [row.xml_index for row in exported] == list(range(len(exported)))
    assert len(exported) == number_of_exported_invoices
    for row in rows:
        assert (row.xml_index is not None) == row.exported


@pytest.mark.parametrize(
    "build, contract_in_document",
    LINKED_SCENARIOS,
    ids=[build.__name__ for build, _ in LINKED_SCENARIOS],
)
@pytest.mark.django_db
def test_part_of_contract_names_a_group_the_document_holds(
    build: Callable[[], None], contract_in_document: bool
) -> None:
    """A link to a contract is only worth publishing with that contract's own invoice group.

    ``part_of_contract`` carries a group id, and an invoice group of the contract's cost block
    carries the same one — a reader joins the publication to the money through it. A contract the
    document holds no invoices for is named without one, since there is no group to share.
    """
    _home_institution()
    build()

    report = _generate()
    document = _document(report)
    assert document is not None and document.publication is not None

    groups_by_esac = {
        contract.primary_identifier.value: contract.cost_data.invoice_group[0].group_id
        for contract in document.contract or []
        if contract.cost_data.invoice_group
    }
    links = [
        publication.cost_data.part_of_contract
        for publication in document.publication
        if publication.cost_data.part_of_contract is not None
    ]
    assert links, "the scenario exports no contract link to check"

    for link in links:
        assert link.primary_identifier is not None
        esac = link.primary_identifier.value
        if link.group_id is None:
            assert esac not in groups_by_esac
        else:
            assert groups_by_esac[esac] == link.group_id

    assert any(link.group_id is not None for link in links) is contract_in_document


@pytest.mark.parametrize("build", SCENARIOS, ids=lambda build: build.__name__)
@pytest.mark.django_db
def test_stored_issue_log_reads_issue_by_issue_and_matches_the_counts(
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
def test_a_document_that_cannot_be_built_fails_the_generation_it_was_run_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is one transform and one artifact: a broken one is heard, not written around."""

    _clean_publication()

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the artifact cannot be built today")

    monkeypatch.setattr(report_service, "transform_report", broken)

    with pytest.raises(RuntimeError, match="cannot be built today"):
        _generate()

    report = OpenCostReport.objects.get()
    assert (report.xml_content, report.issues) == ("", [])
    # The run left nothing behind for the document to be missing from, either.
    assert not OpenCostReportPublication.objects.filter(report=report).exists()


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
    # The two values the document cannot state for a publication of its own are the row's.
    assert publication.title == "Clean article"
    assert publication.publisher != ""


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

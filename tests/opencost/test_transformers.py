"""The openCost document a report states, element by element.

Generation reads a CODA record and writes what openCost can be told about it. Where the schema
has no room for a value, the document says less rather than failing; where a whole item cannot be
stated, it is left out and the reason is written to the report's issue log. These tests put one
shape of CODA data in front of that rule at a time and read the stored document back.

An item the schema cannot be given is reported instead of exported, so a test asserting an
exclusion asserts an empty document and one issue, never a silently shortened one.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from coda.apps.contracts.models import Contract, ContractLink, ContractLinkType
from coda.apps.institutions.models import InstitutionLink, InstitutionLinkType
from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.report_service import generate_report
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import Link, LinkType
from coda.apps.publications.models._attachedentities import PublicationAttachedConcept
from coda.apps.publications.models._vocabulary import Vocabulary
from coda.domain.contract import PublicationBilling
from opencost import (
    CoarPublicationType,
    ContractPrimaryIdentifierType,
    ContractSecondaryIdTypeEnum,
    ContractType,
    InstitutionIdType,
    InstitutionNameType,
    PublicationCostType,
    PublicationSecondaryIdTypeEnum,
    PublicationType,
)
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

FILTERS = {
    "period_start": date(2024, 1, 1).isoformat(),
    "period_end": date(2024, 12, 31).isoformat(),
}


def _generate() -> OpenCostReport:
    """The report the test's own records make up, home institution and all."""
    return create_opencost_report()


def _generate_without_home_institution() -> OpenCostReport:
    """The same, with no home institution to fall back to.

    A record that names no institution of its own then has nothing left to be named by.
    """
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = None
    prefs.save()
    return generate_report(title="Report without a home institution", filters=FILTERS)


def _exported_publication(report: OpenCostReport) -> PublicationType:
    """The one publication the report exports."""
    publications = stored_document(report).publication or []
    assert len(publications) == 1
    return publications[0]


def _exported_contract(report: OpenCostReport) -> ContractType:
    """The one contract the report exports."""
    contracts = stored_document(report).contract or []
    assert len(contracts) == 1
    return contracts[0]


def _issues(report: OpenCostReport) -> list[ValidationWarning]:
    """The report's issue log, read back as the warnings it was written from."""
    return [ValidationWarning(**issue) for issue in report.issues]


# ---------------------------------------------------------------------------------------------
# The publication's own identity


@pytest.mark.django_db
def test__article_without_doi__the_document_names_it_by_title_and_publisher() -> None:
    fr = modelfactory.fundingrequest(title="Invoice Test Publication")
    fr.publication.online_publication_date = date(2024, 5, 15)
    fr.publication.links.filter(type__name="DOI").delete()
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
    )

    publication = _exported_publication(_generate())

    assert publication.primary_identifier.doi is None
    bibliographic = publication.primary_identifier.bibliographic_information
    assert bibliographic is not None
    assert bibliographic.Title == "Invoice Test Publication"
    assert bibliographic.Publisher not in (None, "")


@pytest.mark.django_db
def test__monograph_without_doi__the_document_names_its_publisher() -> None:
    publisher = modelfactory.publisher(name="Academic Press")
    fr = modelfactory.fundingrequest(title="Test Monograph")
    fr.publication.article_journal = None
    fr.publication.monograph_publisher = publisher
    fr.publication.links.filter(type__name="DOI").delete()
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-MONO-001",
        cost_amount=Decimal("2000.00"),
        cost_type="other",
    )

    publication = _exported_publication(_generate())

    bibliographic = publication.primary_identifier.bibliographic_information
    assert bibliographic is not None
    assert bibliographic.Title == "Test Monograph"
    assert "Academic Press" in bibliographic.Publisher


@pytest.mark.django_db
def test__publication_with_a_doi__the_document_carries_it_as_its_primary_identifier() -> None:
    fr = modelfactory.fundingrequest(title="Test Publication with DOI")

    create_publication_with_invoice(
        publication=fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-DOI-001",
    )

    publication = _exported_publication(_generate())

    assert publication.primary_identifier.doi == "10.1234/5678"  # domainfactory default


@pytest.mark.django_db
def test__publication_with_a_coar_type__the_document_carries_that_type() -> None:
    fr = modelfactory.fundingrequest(title="Test Publication with a COAR publication type")

    vocabulary = Vocabulary.objects.create(name="COAR", version="1.0")
    coar_concept = PublicationAttachedConcept.objects.create(
        vocabulary=vocabulary, name="conference paper"
    )
    fr.publication.publication_type = coar_concept
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-COAR-001",
    )

    assert _exported_publication(_generate()).publication_type == (
        CoarPublicationType.conference_paper
    )


@pytest.mark.django_db
def test__publication_with_a_type_outside_coar__the_document_falls_back_to_other() -> None:
    """A concept name outside the COAR vocabulary must not abort the export."""
    fr = modelfactory.fundingrequest(title="Test Publication with a non-COAR publication type")

    vocabulary = Vocabulary.objects.create(name="Local", version="1.0")
    unknown_concept = PublicationAttachedConcept.objects.create(
        vocabulary=vocabulary, name="Unknown"
    )
    fr.publication.publication_type = unknown_concept
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 22),
        invoice_number="INV-COAR-002",
    )

    assert _exported_publication(_generate()).publication_type == CoarPublicationType.other


@pytest.mark.django_db
def test__publication_with_links__the_document_carries_their_opencost_kinds() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Secondary IDs")

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=fr.publication, type=handle_type, value="hdl:1234/5678")

    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    Link.objects.create(publication=fr.publication, type=urn_type, value="urn:nbn:de:1234-5678")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-COAR-001",
    )

    secondary = _exported_publication(_generate()).secondary_identifiers
    assert secondary is not None
    identifiers = secondary.id or []
    assert len(identifiers) == 3  # ISBN (factory) + Handle + URN

    handles = [
        secondary_id
        for secondary_id in identifiers
        if secondary_id.type == PublicationSecondaryIdTypeEnum.handle
    ]
    assert [secondary_id.value for secondary_id in handles] == ["hdl:1234/5678"]

    urns = [
        secondary_id
        for secondary_id in identifiers
        if secondary_id.type == PublicationSecondaryIdTypeEnum.urn
    ]
    assert [secondary_id.value for secondary_id in urns] == ["urn:nbn:de:1234-5678"]


@pytest.mark.django_db
def test__publication_link_of_a_kind_opencost_lacks__the_document_leaves_that_link_out() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Web Link")

    url_type, _ = LinkType.objects.get_or_create(name="URL")
    Link.objects.create(
        publication=fr.publication,
        type=url_type,
        value="https://example.org/articles/4711",
    )

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=fr.publication, type=handle_type, value="hdl:12345/9876")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-UNMAPPABLE-001",
    )

    secondary = _exported_publication(_generate()).secondary_identifiers
    assert secondary is not None
    values = [secondary_id.value for secondary_id in secondary.id or []]

    assert "https://example.org/articles/4711" not in values
    assert "hdl:12345/9876" in values
    assert len(values) == 2  # ISBN (factory) + handle


@pytest.mark.django_db
def test__publication_with_only_links_opencost_lacks__the_document_omits_the_block() -> None:
    """openCost forbids an empty identifier block, so it is left out rather than written empty."""
    fr = modelfactory.fundingrequest(title="Publication With Unmappable Links Only")
    fr.publication.links.exclude(type__name="DOI").delete()

    url_type, _ = LinkType.objects.get_or_create(name="URL")
    Link.objects.create(
        publication=fr.publication,
        type=url_type,
        value="https://example.org/articles/4712",
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 21),
        invoice_number="INV-UNMAPPABLE-002",
    )

    assert _exported_publication(_generate()).secondary_identifiers is None


@pytest.mark.django_db
def test__publication_link_without_a_value__the_document_leaves_that_link_out() -> None:
    fr = modelfactory.fundingrequest(title="Publication With Empty Link Value")

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=fr.publication, type=handle_type, value="hdl:12345/9877")
    Link.objects.create(publication=fr.publication, type=handle_type, value="")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 22),
        invoice_number="INV-EMPTY-VALUE-001",
    )

    secondary = _exported_publication(_generate()).secondary_identifiers
    assert secondary is not None
    values = [secondary_id.value for secondary_id in secondary.id or []]

    assert "" not in values
    assert "hdl:12345/9877" in values
    assert len(values) == 2  # ISBN (factory) + handle


# ---------------------------------------------------------------------------------------------
# The institution the publication is credited to


@pytest.mark.django_db
def test__publication_of_a_known_institution__the_document_names_it_and_its_identifiers() -> None:
    institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/test123",
        isni="0000 0001 2345 6789",
    )

    fr = modelfactory.fundingrequest(title="Test Publication")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(
        publication=fr.publication,
        name="Test Author",
        email="test@example.com",
        affiliation=institution,
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )

    reported = _exported_publication(_generate()).institution
    assert reported is not None
    assert [(name.value, name.type) for name in reported.name or []] == [
        ("Test University", InstitutionNameType.full)
    ]
    assert reported.id is not None

    rors = [identifier for identifier in reported.id if identifier.type == InstitutionIdType.ror]
    assert [identifier.value for identifier in rors] == ["https://ror.org/test123"]

    isnis = [identifier for identifier in reported.id if identifier.type == InstitutionIdType.isni]
    assert [identifier.value for identifier in isnis] == ["0000 0001 2345 6789"]


@pytest.mark.django_db
def test__institution_identifier_opencost_cannot_state__the_document_leaves_that_one_out() -> None:
    """An identifier of an unknown kind, and one with nothing in it, are both unstaterable."""
    institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/guard123",
    )
    other_type, _ = InstitutionLinkType.objects.get_or_create(name="OtherID")
    InstitutionLink.objects.create(
        institution=institution, type=other_type, value="https://example.org/no-identifier-scheme"
    )
    isni_type, _ = InstitutionLinkType.objects.get_or_create(name="ISNI")
    InstitutionLink.objects.create(institution=institution, type=isni_type, value="")

    fr = modelfactory.fundingrequest(title="Publication with bad institution identifiers")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(publication=fr.publication, affiliation=institution)

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-INSTITUTION-GUARD-001",
    )

    reported = _exported_publication(_generate()).institution
    assert reported is not None
    assert [(identifier.type, identifier.value) for identifier in reported.id or []] == [
        (InstitutionIdType.ror, "https://ror.org/guard123")
    ]


@pytest.mark.django_db
def test__home_institution_identifier_opencost_cannot_state__the_document_leaves_that_one_out() -> (
    None
):
    """A contract is named by the home institution, whose identifiers go through the same rule."""
    home_institution = create_institution_with_identifiers(
        name="Home University",
        ror="https://ror.org/guard456",
    )
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()
    other_type, _ = InstitutionLinkType.objects.get_or_create(name="OtherID")
    InstitutionLink.objects.create(
        institution=home_institution,
        type=other_type,
        value="https://example.org/no-identifier-scheme",
    )
    isni_type, _ = InstitutionLinkType.objects.get_or_create(name="ISNI")
    InstitutionLink.objects.create(institution=home_institution, type=isni_type, value="")

    contract = create_contract_with_identifiers(name="Guard Agreement")
    create_contract_with_invoice(contract)

    reported = _exported_contract(_generate()).institution
    assert reported is not None
    assert [(identifier.type, identifier.value) for identifier in reported.id or []] == [
        (InstitutionIdType.ror, "https://ror.org/guard456")
    ]


# ---------------------------------------------------------------------------------------------
# The invoices a publication was given


@pytest.mark.django_db
def test__publication_invoice__the_document_states_its_amount_as_the_position_records_it() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Invoice")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
        cost_amount=Decimal("1500.00"),
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None

    invoice = invoices[0]
    assert invoice.invoice_number == "INV-2024-001"
    assert invoice.creditor == "Invoice Creditor"
    assert invoice.dates.invoice == "2024-06-01"

    assert invoice.amount_invoice is not None
    assert invoice.amount_invoice.amount == Decimal("1500.00")
    assert invoice.amount_invoice.currency == "EUR"

    assert len(invoice.amounts_paid.amount_paid) == 1
    amount_paid = invoice.amounts_paid.amount_paid[0]
    assert amount_paid.amount == Decimal("1500.00")
    assert amount_paid.currency == "EUR"
    assert amount_paid.cost_type == PublicationCostType.gold_oa
    assert amount_paid.vat == Decimal("285.00")


@pytest.mark.django_db
def test__invoice_of_two_positions__the_document_gives_both_amounts_of_that_one_invoice() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Invoice and Multiple Positions")

    invoice = create_invoice(
        creditor=create_creditor(name="Invoice Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-2024-002",
    )
    create_position(
        invoice,
        fr.publication,
        description="APC for test article - Part 1",
        cost_amount=Decimal("1000.00"),
    )
    create_position(
        invoice,
        fr.publication,
        description="APC for test article - Part 2",
        cost_amount=Decimal("500.00"),
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None
    assert len(invoices) == 1

    exported = invoices[0]
    assert exported.invoice_number == "INV-2024-002"
    assert exported.amount_invoice is not None
    assert exported.amount_invoice.amount == Decimal("1500.00")  # 1000 + 500
    assert exported.amount_invoice.currency == "EUR"

    amounts = exported.amounts_paid.amount_paid
    assert [amount_paid.amount for amount_paid in amounts] == [
        Decimal("500.00"),
        Decimal("1000.00"),
    ]


@pytest.mark.django_db
def test__invoice_of_two_currencies__the_document_totals_every_row_it_was_given() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Invoice in Mixed Currencies")

    invoice = create_invoice(
        creditor=create_creditor(name="Mixed Currency Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-2024-004",
    )
    create_position(
        invoice, fr.publication, description="APC in euros", cost_amount=Decimal("1000.00")
    )
    create_position(
        invoice,
        fr.publication,
        description="APC in dollars",
        cost_amount=Decimal("500.00"),
        cost_currency="USD",
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None

    exported = invoices[0]
    # every row is part of the total, whatever its currency: this is the number stated on the
    # invoice, and an invoice carries one currency in CODA
    assert exported.amount_invoice is not None
    assert exported.amount_invoice.amount == Decimal("1500.00")
    assert exported.amount_invoice.currency == "USD"

    amounts = exported.amounts_paid.amount_paid
    assert [amount_paid.currency for amount_paid in amounts] == ["USD", "EUR"]


@pytest.mark.django_db
def test__invoice_of_a_sub_cent_amount__the_document_states_the_amount_at_its_own_precision() -> (
    None
):
    """A CODA amount of four decimals reaches the document at the two it carries.

    The invoice is exported either way, with the position's amount and the tax computed from it,
    read back as the document states them — the half cent is the document's, not the report's,
    business.
    """
    fr = modelfactory.fundingrequest(title="Publication with a Four Decimal Place Amount")

    invoice = create_invoice(
        creditor=create_creditor(name="Precision Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-2024-PRECISION",
    )
    create_position(
        invoice,
        fr.publication,
        description="APC with a half cent",
        cost_amount=Decimal("1000.0050"),
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None

    amount_paid = invoices[0].amounts_paid.amount_paid[0]
    assert amount_paid.amount == Decimal("1000.00")
    assert amount_paid.vat == Decimal("190.00")
    assert invoices[0].amount_invoice is not None
    assert invoices[0].amount_invoice.amount == Decimal("1000.00")


@pytest.mark.django_db
def test__publication_of_two_invoices__the_document_holds_both_invoices() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Multiple Invoices")

    invoice1 = create_invoice(
        creditor=create_creditor(name="First Creditor"),
        invoice_date=date(2024, 5, 1),
        number="INV-2024-101",
    )
    create_position(
        invoice1,
        fr.publication,
        description="APC for test article - Invoice 1",
        cost_amount=Decimal("800.00"),
    )

    invoice2 = create_invoice(
        creditor=create_creditor(name="Second Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-2024-102",
    )
    create_position(
        invoice2,
        fr.publication,
        description="APC for test article - Invoice 2",
        cost_amount=Decimal("700.00"),
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None
    assert [invoice.invoice_number for invoice in invoices] == ["INV-2024-101", "INV-2024-102"]


@pytest.mark.django_db
def test__invoice_without_number_or_creditor__the_document_omits_both_elements() -> None:
    """openCost rejects an empty string, so a blank field is left out rather than written blank."""
    fr = modelfactory.fundingrequest(title="Publication with blank invoice fields")
    invoice = create_invoice(
        creditor=create_creditor(name=""),
        invoice_date=date(2024, 6, 1),
        number="",
    )
    create_position(invoice, fr.publication, cost_amount=Decimal("1500.00"))

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None

    exported = invoices[0]
    assert exported.invoice_number is None
    assert exported.creditor is None
    assert exported.amounts_paid.amount_paid[0].amount == Decimal("1500.00")


@pytest.mark.django_db
def test__position_of_an_unknown_cost_type__the_document_holds_the_other_positions() -> None:
    fr = modelfactory.fundingrequest(title="Publication with unmappable cost type")
    invoice = create_invoice(
        creditor=create_creditor("Cost Type Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-COST-TYPE-001",
    )
    create_position(
        invoice,
        fr.publication,
        description="APC",
        cost_amount=Decimal("1000.00"),
        cost_type="gold-oa",
    )
    create_position(
        invoice,
        fr.publication,
        description="Surcharge",
        cost_amount=Decimal("200.00"),
        cost_type="service fee",
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None

    amounts_paid = invoices[0].amounts_paid.amount_paid
    assert len(amounts_paid) == 1
    assert amounts_paid[0].cost_type == PublicationCostType.gold_oa
    assert amounts_paid[0].amount == Decimal("1000.00")

    # the total is the price stated on the invoice, so the rejected row is still in it
    assert invoices[0].amount_invoice is not None
    assert invoices[0].amount_invoice.amount == Decimal("1200.00")


@pytest.mark.django_db
def test__invoice_of_no_stateable_amount__the_publication_is_left_out_of_the_document() -> None:
    """No amount means no invoice block, and then the publication has no cost data at all."""
    fr = modelfactory.fundingrequest(title="Publication with only unmappable positions")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-COST-TYPE-002",
        cost_type="service fee",
    )

    report = _generate()

    assert report.xml_content == ""
    assert report.publications.get().exported is False


@pytest.mark.django_db
def test__position_of_a_currency_opencost_pattern_accepts__the_document_carries_it() -> None:
    """ISO membership is CODA's business; the pattern is openCost's, and it is what is checked."""
    fr = modelfactory.fundingrequest(title="Publication with non-ISO currency")
    invoice = create_invoice(
        creditor=create_creditor("Non ISO Currency Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-COST-TYPE-003",
    )
    create_position(
        invoice,
        fr.publication,
        description="APC",
        cost_amount=Decimal("1000.00"),
        cost_currency="XYZ",
    )

    invoices = _exported_publication(_generate()).cost_data.invoice
    assert invoices is not None

    amount_paid = invoices[0].amounts_paid.amount_paid[0]
    assert amount_paid.currency == "XYZ"


# ---------------------------------------------------------------------------------------------
# The contract and its cost data


@pytest.mark.django_db
def test__contract__the_document_names_the_home_institution_and_its_participation() -> None:
    """A contract is credited to the home institution, with the contract's own dates.

    CODA records no institution of a contract's own, so the report can only state the one it was
    run for — and openCost requires the participation block, whose dates come from the contract.
    """
    home_institution = create_institution_with_identifiers(
        name="University of Testing",
        ror="https://ror.org/test123",
        isni="0000 0001 2345 6789",
    )
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    contract = create_contract_with_identifiers(
        name="Test Transform Agreement",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    create_contract_with_invoice(contract)

    contract_data = _exported_contract(_generate())

    assert contract_data.contract_name == "Test Transform Agreement"
    assert contract_data.institution is not None
    assert [(name.value, name.type) for name in contract_data.institution.name or []] == [
        ("University of Testing", InstitutionNameType.full)
    ]
    assert contract_data.institution.id is not None
    assert {(identifier.type, identifier.value) for identifier in contract_data.institution.id} == {
        (InstitutionIdType.ror, "https://ror.org/test123"),
        (InstitutionIdType.isni, "0000 0001 2345 6789"),
    }
    assert (contract_data.participation.from_, contract_data.participation.to) == (
        "2024-01-01",
        "2024-12-31",
    )


@pytest.mark.django_db
def test__contract_invoice__the_document_states_its_period_and_the_invoice_as_billed() -> None:
    contract = Contract.objects.create(
        name="Test Invoice Contract",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        publication_billing=PublicationBilling.Individually.value,
    )

    create_contract_with_invoice(
        contract=contract,
        invoice_date=date(2024, 7, 1),
        invoice_number="INV-CONTRACT-001",
    )

    groups = _exported_contract(_generate()).cost_data.invoice_group
    assert groups is not None
    assert len(groups) == 1

    group = groups[0]
    assert group.invoices_period is not None
    assert (group.invoices_period.from_, group.invoices_period.to) == (
        "2024-01-01",
        "2024-12-31",
    )

    invoices = group.invoice or []
    assert len(invoices) == 1
    assert invoices[0].invoice_number == "INV-CONTRACT-001"
    assert invoices[0].creditor == "Contract Creditor"
    assert invoices[0].dates.invoice == "2024-07-01"
    assert invoices[0].amount_invoice is not None
    assert invoices[0].amount_invoice.amount == Decimal("1200.00")
    assert invoices[0].amount_invoice.currency == "EUR"


@pytest.mark.django_db
def test__contract_invoice_of_two_positions__the_document_gives_both_amounts() -> None:
    contract = Contract.objects.create(
        name="Test Invoice Contract Multiple Positions",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        publication_billing=PublicationBilling.Individually.value,
    )

    create_contract_with_invoice(
        contract=contract,
        invoice_date=date(2024, 8, 1),
        invoice_number="INV-CONTRACT-002",
        position_descriptions=["Service Fee Part 1", "Service Fee Part 2"],
        position_amounts=[Decimal("700.00"), Decimal("500.00")],
    )

    groups = _exported_contract(_generate()).cost_data.invoice_group
    assert groups is not None
    invoices = groups[0].invoice or []

    assert invoices[0].amount_invoice is not None
    assert invoices[0].amount_invoice.amount == Decimal("1200.00")  # 700 + 500
    assert invoices[0].amount_invoice.currency == "EUR"

    amounts = invoices[0].amounts_paid.amount_paid
    assert [amount_paid.amount for amount_paid in amounts] == [
        Decimal("500.00"),
        Decimal("700.00"),
    ]


@pytest.mark.django_db
def test__contract_with_an_esac_id__the_document_names_it_by_that_and_no_other_link() -> None:
    contract = create_contract_with_identifiers(
        esac="https://esac.org/id/123456",
    )

    other_type, _ = ContractLinkType.objects.get_or_create(name="OtherID")
    ContractLink.objects.create(
        contract=contract, type=other_type, value="https://otherid.com/id/555555"
    )

    invoice = create_invoice(
        creditor=create_creditor(name="Contract Creditor"),
        invoice_date=date(2024, 8, 1),
        number="INV-CONTRACT-ESAC-002",
        status="paid",
    )
    create_position(
        invoice,
        contract=contract,
        description="Service Fee",
        cost_amount=Decimal("700.00"),
        cost_type="publish",
    )

    primary_identifier = _exported_contract(_generate()).primary_identifier
    assert primary_identifier.type == ContractPrimaryIdentifierType.ESAC
    assert primary_identifier.value == "https://esac.org/id/123456"


@pytest.mark.django_db
def test__contract_with_other_identifiers__the_document_carries_each_by_its_kind() -> None:
    contract = create_contract_with_identifiers(
        oai="https://services.dnb.de/oai/repository/789012",
        ezb="https://ezb.uni-regensburg.de/id/456789",
        local="LOCAL-ID-001",
    )

    invoice = create_invoice(
        creditor=create_creditor(name="Contract Creditor"),
        invoice_date=date(2024, 8, 1),
        number="INV-CONTRACT-SECONDARY-002",
        status="paid",
    )
    create_position(
        invoice,
        contract=contract,
        description="Service Fee",
        cost_amount=Decimal("700.00"),
        cost_type="publish",
    )

    secondary = _exported_contract(_generate()).secondary_identifiers
    assert secondary is not None
    assert {(identifier.type, identifier.value) for identifier in secondary.id or []} == {
        (ContractSecondaryIdTypeEnum.oai, "https://services.dnb.de/oai/repository/789012"),
        (ContractSecondaryIdTypeEnum.ezb, "https://ezb.uni-regensburg.de/id/456789"),
        (ContractSecondaryIdTypeEnum.local, "LOCAL-ID-001"),
    }


@pytest.mark.django_db
def test__publication_under_a_contract__the_document_links_it_to_that_contract() -> None:
    contract = create_contract_with_identifiers(
        esac="https://esac.org/id/test-contract-123",
    )

    fr = modelfactory.fundingrequest(title="Publication with Attached Contract")
    fr.publication.attached_contracts.create(contract=contract, contract_year=2024)

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
    )

    cost_data = _exported_publication(_generate()).cost_data
    assert cost_data.invoice is not None
    assert len(cost_data.invoice or []) == 1

    part_of_contract = cost_data.part_of_contract
    assert part_of_contract is not None
    assert part_of_contract.primary_identifier is not None
    assert part_of_contract.primary_identifier.type == ContractPrimaryIdentifierType.ESAC
    assert part_of_contract.primary_identifier.value == "https://esac.org/id/test-contract-123"


# ---------------------------------------------------------------------------------------------
# What the report says when a record cannot be stated


@pytest.mark.django_db
def test__contract_without_participation_dates__the_document_holds_no_contract() -> None:
    """openCost requires both participation dates, so the contract cannot be reported at all."""
    contract = create_contract_with_identifiers(name="Undated Agreement")
    contract.start_date = None
    contract.end_date = None
    contract.save()
    create_contract_with_invoice(contract)

    report = _generate()

    assert report.xml_content == ""

    issues = _issues(report)
    assert len(issues) == 1
    assert issues[0].level == "error"
    assert issues[0].entity_type == "contract"
    assert issues[0].entity_name == "Undated Agreement"
    assert "participation" in issues[0].message


@pytest.mark.django_db
def test__invoice_of_no_stateable_amount__the_publication_reports_one_issue() -> None:
    """The invoice and the publication both go, but a single entry tells the whole story."""
    fr = modelfactory.fundingrequest(title="Publication with no reportable positions")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-COST-TYPE-004",
        cost_type="service fee",
    )

    report = _generate()

    issues = _issues(report)
    assert len(issues) == 1
    assert "Excluded entirely" in issues[0].message
    assert "INV-COST-TYPE-004" in issues[0].message


@pytest.mark.django_db
def test__partly_stateable_invoice__the_report_says_which_row_it_lost() -> None:
    fr = modelfactory.fundingrequest(title="Publication with a partial invoice")
    invoice = create_invoice(
        creditor=create_creditor("Cost Type Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-COST-TYPE-005",
    )
    create_position(
        invoice,
        fr.publication,
        description="APC",
        cost_amount=Decimal("1000.00"),
        cost_type="gold-oa",
    )
    create_position(
        invoice,
        fr.publication,
        description="Surcharge",
        cost_amount=Decimal("200.00"),
        cost_type="service fee",
    )

    report = _generate()

    issues = _issues(report)
    assert len(issues) == 1
    assert issues[0].entity_type == "publication"
    assert "INV-COST-TYPE-005" in issues[0].message
    assert "service fee" in issues[0].message


@pytest.mark.django_db
def test__publication_without_institution__the_report_points_at_the_preferences() -> None:
    """Nothing names this publication's institution: the fix is a preference, and the report says so."""
    fr = modelfactory.fundingrequest(title="Publication without institution data")
    fr.publication.relevant_authors.all().delete()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-NOINST-PUB-001",
    )

    report = _generate_without_home_institution()

    issues = _issues(report)
    assert len(issues) == 1
    assert issues[0].entity_type == "global"
    assert issues[0].entity_name == fr.publication.title
    assert "institution" in issues[0].message
    assert issues[0].fix_url == reverse("preferences:global_preferences")


@pytest.mark.django_db
def test__contract_without_institution__the_report_points_at_the_preferences() -> None:
    contract = create_contract_with_identifiers(name="Agreement without institution data")
    create_contract_with_invoice(contract, invoice_number="INV-NOINST-CON-001")

    report = _generate_without_home_institution()

    issues = _issues(report)
    assert len(issues) == 1
    assert issues[0].entity_type == "global"
    assert issues[0].entity_name == "Agreement without institution data"
    assert "institution" in issues[0].message
    assert issues[0].fix_url == reverse("preferences:global_preferences")


@pytest.mark.django_db
def test__excluded_publication__its_issue_links_to_the_request_it_was_filed_under() -> None:
    """The issue offers the record a reader can fix — the request, not the publication row."""
    # A decoy publication first: the factories would otherwise allocate the publication and
    # the funding request the same primary key, hiding a wrong-id fix URL.
    modelfactory.publication(title="Decoy publication to desync identifiers")
    fr = modelfactory.fundingrequest(title="Publication whose exclusion links home")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-FIXURL-001",
        cost_type="service fee",
    )

    issues = _issues(_generate())

    assert len(issues) == 1
    assert issues[0].fix_url == reverse("fundingrequests:detail", kwargs={"pk": fr.pk})
    assert issues[0].fix_url != reverse("fundingrequests:detail", kwargs={"pk": fr.publication_id})


@pytest.mark.django_db
def test__excluded_publication_never_filed_under_a_request__its_issue_carries_no_link() -> None:
    """A publication that came to CODA by itself has no request to point a reader at."""
    publication = modelfactory.publication(title="Imported publication without a request")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-FIXURL-002",
        cost_type="service fee",
    )

    issues = _issues(_generate())

    assert len(issues) == 1
    assert issues[0].entity_name == publication.title
    assert issues[0].fix_url is None


@pytest.mark.django_db
def test__contract_without_esac__the_document_substitutes_and_the_report_says_so() -> None:
    contract = create_contract_with_identifiers(name="No ESAC Agreement")
    create_contract_with_invoice(contract)

    report = _generate()

    assert _exported_contract(report).primary_identifier.value == "UNKNOWN"

    issues = _issues(report)
    assert len(issues) == 1
    assert issues[0].level == "warning"
    assert issues[0].entity_type == "contract"
    assert issues[0].entity_name == "No ESAC Agreement"
    assert issues[0].message == "No ESAC ID — the contract is exported with ESAC 'UNKNOWN'."


@pytest.mark.django_db
def test__publication_without_doi__the_document_substitutes_and_the_report_says_so() -> None:
    fr = modelfactory.fundingrequest(title="Publication without DOI")
    fr.publication.links.filter(type__name="DOI").delete()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-NODOI-001",
    )

    report = _generate()

    assert _exported_publication(report).primary_identifier.doi is None

    issues = _issues(report)
    assert len(issues) == 1
    assert issues[0].level == "warning"
    assert issues[0].entity_type == "publication"
    assert issues[0].message == (
        "No DOI — the publication is exported with title and journal instead."
    )


@pytest.mark.django_db
def test__publication_without_publisher__the_document_substitutes_both_values() -> None:
    fr = modelfactory.fundingrequest(title="Publication without publisher")
    fr.publication.links.filter(type__name="DOI").delete()
    fr.publication.article_journal = None
    fr.publication.save()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-NOPUB-001",
    )

    report = _generate()

    bibliographic = _exported_publication(report).primary_identifier.bibliographic_information
    assert bibliographic is not None
    assert bibliographic.Publisher == "Unknown Publisher"

    issues = _issues(report)
    assert [issue.message for issue in issues] == [
        "No DOI — the publication is exported with title and journal instead.",
        "No publisher — the publication is exported with 'Unknown Publisher'.",
    ]

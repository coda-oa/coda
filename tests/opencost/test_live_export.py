import pytest

from coda.apps.contracts.models import Contract
from coda.apps.opencost.live_export import to_publication
from coda.apps.publications.models._attachedentities import (
    AttachedContract,
    PublicationAttachedConcept,
)
from coda.apps.publications.models._vocabulary import Vocabulary
from coda.domain.opencost import PublicationType
from tests import modelfactory
from coda.apps.publications.models import LinkType, Link
from coda.apps.publications.models import Publication as PublicationModel
from coda.domain.opencost import CoarPublicationType
from coda.domain.opencost import PublicationSecondaryIdTypeEnum
from coda.domain.opencost._types import PublicationCostType
from tests.opencost.helpers import (
    create_creditor,
    create_publication_with_invoice,
    create_invoice,
    create_position,
)
from decimal import Decimal
from datetime import date


@pytest.mark.django_db
def test__coda_article_publication__transforming_to_opencost__returns_valid_opencost_publication() -> (
    None
):
    publication = modelfactory.publication(title="Test Article About Costs")

    result = to_publication(publication)

    assert isinstance(result, PublicationType)
    assert result.primary_identifier.bibliographic_information is not None
    assert result.primary_identifier.bibliographic_information.Title == "Test Article About Costs"

    assert publication.article_journal is not None
    assert (
        publication.article_journal.publisher.name
        in result.primary_identifier.bibliographic_information.Publisher
    )
    assert (
        publication.article_journal.title
        in result.primary_identifier.bibliographic_information.isPartOf
    )


@pytest.mark.django_db
def test__coda_monograph_publication__transforming_to_opencost__returns_valid_opencost_publication() -> (
    None
):
    publisher = modelfactory.publisher(name="Academic Press")
    publication = PublicationModel.objects.create(
        title="Test Monograph",
        monograph_publisher=publisher,
    )

    result = to_publication(publication)

    assert isinstance(result, PublicationType)
    assert result.primary_identifier.bibliographic_information is not None
    assert result.primary_identifier.bibliographic_information.Title == "Test Monograph"
    assert "Academic Press" in result.primary_identifier.bibliographic_information.Publisher


@pytest.mark.django_db
def test__publication_with_doi__transforming_to_opencost__doi_is_included_in_primary_identifier() -> (
    None
):
    publication = modelfactory.publication(title="Test Publication with DOI")
    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    Link.objects.create(
        publication=publication,
        type=doi_type,
        value="10.1234/test.doi",
    )

    oc_publication = to_publication(publication)

    assert oc_publication.primary_identifier.doi == "10.1234/test.doi"


@pytest.mark.django_db
def test__publication_with_publication_types__transforming_to_opencost__publication_types_are_included() -> (
    None
):
    publication = modelfactory.publication(title="Test Publication with a COAR publication type")

    vocabulary = Vocabulary.objects.create(name="COAR", version="1.0")

    coar_concept = PublicationAttachedConcept.objects.create(
        vocabulary=vocabulary, name="conference paper"
    )
    publication.publication_type = coar_concept
    publication.save()

    oc_publication = to_publication(publication)

    assert oc_publication.publication_type == CoarPublicationType.conference_paper


@pytest.mark.django_db
def test__publication_with_no_doi_but_bibliographic_info__transforming_to_opencost__bibliographic_info_is_included() -> (
    None
):
    publication = modelfactory.publication(title="Publication without DOI")

    oc_publication = to_publication(publication)

    assert oc_publication.primary_identifier.bibliographic_information is not None
    assert (
        oc_publication.primary_identifier.bibliographic_information.Title
        == "Publication without DOI"
    )
    # Joural Info
    assert publication.article_journal is not None
    assert (
        publication.article_journal.publisher.name
        in oc_publication.primary_identifier.bibliographic_information.Publisher
    )
    assert (
        publication.article_journal.title
        in oc_publication.primary_identifier.bibliographic_information.isPartOf
    )


@pytest.mark.django_db
def test__publication_with_secondary_identifiers__transforming_to_opencost__secondary_identifiers_are_included() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Secondary IDs")

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=publication, type=handle_type, value="hdl:1234/5678")

    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    Link.objects.create(publication=publication, type=urn_type, value="urn:nbn:de:1234-5678")

    oc_publication = to_publication(publication)

    assert oc_publication.secondary_identifiers is not None
    assert len(oc_publication.secondary_identifiers.id) == 2

    handle_ids = [
        sid
        for sid in oc_publication.secondary_identifiers.id
        if sid.type == PublicationSecondaryIdTypeEnum.handle
    ]
    assert len(handle_ids) == 1
    assert handle_ids[0].value == "hdl:1234/5678"

    urn_ids = [
        sid
        for sid in oc_publication.secondary_identifiers.id
        if sid.type == PublicationSecondaryIdTypeEnum.urn
    ]
    assert len(urn_ids) == 1
    assert urn_ids[0].value == "urn:nbn:de:1234-5678"


@pytest.mark.django_db
def test__publication_with_invoice__transforming_to_opencost__cost_data_includes_invoice_with_correct_position_data() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Invoice")

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
        cost_amount=Decimal("1500.00"),
    )

    oc_publication = to_publication(publication)

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None

    invoice_data = oc_publication.cost_data.invoice[0]
    assert invoice_data.invoice_number == "INV-2024-001"
    assert invoice_data.creditor == "Invoice Creditor"

    assert invoice_data.dates.invoice == "2024-06-01"

    assert invoice_data.amount_invoice is not None
    assert invoice_data.amount_invoice.amount == Decimal("1500.00")
    assert invoice_data.amount_invoice.currency == "EUR"

    assert len(invoice_data.amounts_paid) == 1
    amount_paid = invoice_data.amounts_paid[0]
    assert amount_paid.amount == Decimal("1500.00")
    assert amount_paid.currency == "EUR"
    assert amount_paid.cost_type == PublicationCostType.gold_oa
    assert amount_paid.vat == Decimal("285.00")


@pytest.mark.django_db
def test__publication_with_invoice_multiple_positions__transforming_to_opencost__amount_invoice_and_amounts_paid_are_correct() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Invoice and Multiple Positions")

    creditor = create_creditor(name="Invoice Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 6, 1), number="INV-2024-002"
    )
    create_position(
        invoice,
        publication,
        description="APC for test article - Part 1",
        cost_amount=Decimal("1000.00"),
    )
    create_position(
        invoice,
        publication,
        description="APC for test article - Part 2",
        cost_amount=Decimal("500.00"),
    )

    oc_publication = to_publication(publication)

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None

    # oc invoice
    invoice_data = oc_publication.cost_data.invoice[0]
    assert invoice_data.invoice_number == "INV-2024-002"

    # Verify amount_invoice
    assert invoice_data.amount_invoice is not None
    assert invoice_data.amount_invoice.amount == Decimal("1500.00")  # 1000 + 500
    assert invoice_data.amount_invoice.currency == "EUR"

    # Verify amounts_paid
    assert len(invoice_data.amounts_paid) == 2
    amounts = sorted(invoice_data.amounts_paid, key=lambda x: x.amount)
    assert amounts[0].amount == Decimal("500.00")
    assert amounts[1].amount == Decimal("1000.00")


@pytest.mark.django_db
def test__publication_with_multiple_invoices__transforming_to_opencost__all_invoices_are_included() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Multiple Invoices")

    creditor1 = create_creditor(name="First Creditor")
    invoice1 = create_invoice(
        creditor=creditor1, invoice_date=date(2024, 5, 1), number="INV-2024-101"
    )
    create_position(
        invoice1,
        publication,
        description="APC for test article - Invoice 1",
        cost_amount=Decimal("800.00"),
    )

    creditor2 = create_creditor(name="Second Creditor")
    invoice2 = create_invoice(
        creditor=creditor2, invoice_date=date(2024, 6, 1), number="INV-2024-102"
    )
    create_position(
        invoice2,
        publication,
        description="APC for test article - Invoice 2",
        cost_amount=Decimal("700.00"),
    )

    oc_publication = to_publication(publication)

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None
    assert len(oc_publication.cost_data.invoice) == 2

    invoice_numbers = {inv.invoice_number for inv in oc_publication.cost_data.invoice}
    assert "INV-2024-101" in invoice_numbers
    assert "INV-2024-102" in invoice_numbers


@pytest.mark.django_db
def test__publication_with_contract__transforming_to_opencost__publication_cost_data_includes_contract() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Contract")

    contract = Contract.objects.create(
        name="Test Transformative Agreement",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    AttachedContract.objects.create(publication=publication, contract=contract, contract_year=2024)

    oc_publication = to_publication(publication)

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.part_of_contract is not None
    assert oc_publication.cost_data.part_of_contract.primary_identifier is not None

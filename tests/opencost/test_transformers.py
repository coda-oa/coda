from datetime import date
from decimal import Decimal
import pytest

from coda.apps.opencost.transformers import report_publication_to_pydantic
from coda.apps.publications.models._attachedentities import PublicationAttachedConcept
from coda.apps.publications.models._vocabulary import Vocabulary
from coda.domain.opencost._publication import PublicationSecondaryIdTypeEnum, PublicationType
from coda.domain.opencost._types import PublicationCostType
from tests import modelfactory
from tests.opencost.helpers import (
    create_creditor,
    create_invoice,
    create_position,
    create_publication_with_invoice,
    create_opencost_report,
)
from coda.apps.publications.models import Publication as PublicationModel
from coda.apps.publications.models import LinkType, Link
from coda.domain.opencost import CoarPublicationType

from coda.apps.institutions.models import Institution, InstitutionLinkType, InstitutionLink
from coda.apps.authors.models import Author
from coda.domain.opencost._institution import InstitutionIdType, InstitutionNameType


@pytest.mark.django_db
def test__report_article_publication__transforming_to_opencost__returns_valid_opencost_publication() -> (
    None
):
    publication = modelfactory.publication(title="Invoice Test Publication")
    publication.online_publication_date = date(2024, 5, 15)
    publication.save()

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
    )

    report = create_opencost_report()

    report_publication = report.publications.first()
    assert report_publication is not None

    result = report_publication_to_pydantic(report_publication)

    assert isinstance(result, PublicationType)
    assert result.primary_identifier.bibliographic_information is not None
    assert result.primary_identifier.bibliographic_information.Title == "Invoice Test Publication"
    assert result.primary_identifier.bibliographic_information.Publisher != ""
    assert result.primary_identifier.bibliographic_information.Publisher is not None


@pytest.mark.django_db
def test__report_monograph_publication__transforming_to_opencost__returns_valid_opencost_publication() -> (
    None
):
    publisher = modelfactory.publisher(name="Academic Press")
    publication = PublicationModel.objects.create(
        title="Test Monograph",
        monograph_publisher=publisher,
    )

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-MONO-001",
        cost_amount=Decimal("2000.00"),
        cost_type="other",
    )
    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    result = report_publication_to_pydantic(report_publication)

    assert isinstance(result, PublicationType)
    assert result.primary_identifier.bibliographic_information is not None
    assert result.primary_identifier.bibliographic_information.Title == "Test Monograph"
    assert "Academic Press" in result.primary_identifier.bibliographic_information.Publisher


@pytest.mark.django_db
def test__report_publication_with_doi__transforming_to_opencost__doi_is_included_in_primary_identifier() -> (
    None
):
    publication = modelfactory.publication(title="Test Publication with DOI")

    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    Link.objects.create(
        publication=publication,
        type=doi_type,
        value="10.1234/test.doi",
    )
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-DOI-001",
    )
    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

    assert oc_publication.primary_identifier.doi == "10.1234/test.doi"


@pytest.mark.django_db
def test__report_publication_with_publication_type__transforming_to_opencost__publication_type_is_included() -> (
    None
):
    publication = modelfactory.publication(title="Test Publication with a COAR publication type")

    vocabulary = Vocabulary.objects.create(name="COAR", version="1.0")

    coar_concept = PublicationAttachedConcept.objects.create(
        vocabulary=vocabulary, name="conference paper"
    )
    publication.publication_type = coar_concept
    publication.save()

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-COAR-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

    assert oc_publication.publication_type == CoarPublicationType.conference_paper


@pytest.mark.django_db
def test__report_publication_with_secondary_identifiers__transforming_to_opencost__secondary_identifiers_are_included() -> (
    None
):
    publication = modelfactory.publication(title="Publication with Secondary IDs")

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=publication, type=handle_type, value="hdl:1234/5678")

    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    Link.objects.create(publication=publication, type=urn_type, value="urn:nbn:de:1234-5678")

    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-COAR-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

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
def test__report_publication_with_institution_data__transforming_to_opencost__institution_data_is_included() -> (
    None
):
    institution = Institution.objects.create(name="Test University")
    ror_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
    InstitutionLink.objects.create(
        institution=institution, type=ror_type, value="https://ror.org/test123"
    )
    isni_type, _ = InstitutionLinkType.objects.get_or_create(name="ISNI")
    InstitutionLink.objects.create(
        institution=institution, type=isni_type, value="0000 0001 2345 6789"
    )
    publication = modelfactory.publication(title="Test Publication")
    Author.objects.create(
        name="Test Author",
        email="test@example.com",
        publication=publication,
        affiliation=institution,
        roles="CORRESPONDING_AUTHOR",
    )
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-2024-001",
    )
    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

    assert oc_publication.institution is not None
    assert oc_publication.institution.name is not None

    assert oc_publication.institution.name[0].value == "Test University"
    assert oc_publication.institution.name[0].type == InstitutionNameType.full

    assert oc_publication.institution.id is not None

    ror_ids = [i for i in oc_publication.institution.id if i.type == InstitutionIdType.ror]
    assert len(ror_ids) == 1
    assert ror_ids[0].value == "https://ror.org/test123"

    isni_ids = [i for i in oc_publication.institution.id if i.type == InstitutionIdType.isni]
    assert len(isni_ids) == 1
    assert isni_ids[0].value == "0000 0001 2345 6789"


@pytest.mark.django_db
def test__report_publication_with_invoice__transforming_to_opencost__cost_data_includes_invoice_with_correct_position_data() -> (
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

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

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
def test__report_publication_with_invoice_multiple_positions__transforming_to_opencost__amount_invoice_and_amounts_paid_are_correct() -> (
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

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None

    invoice_data = oc_publication.cost_data.invoice[0]
    assert invoice_data.invoice_number == "INV-2024-002"

    assert invoice_data.amount_invoice is not None
    assert invoice_data.amount_invoice.amount == Decimal("1500.00")  # 1000 + 500
    assert invoice_data.amount_invoice.currency == "EUR"

    assert len(invoice_data.amounts_paid) == 2
    amounts = sorted(invoice_data.amounts_paid, key=lambda x: x.amount)
    assert amounts[0].amount == Decimal("500.00")
    assert amounts[1].amount == Decimal("1000.00")


@pytest.mark.django_db
def test__report_publication_with_multiple_invoices__transforming_to_opencost__all_invoices_are_included() -> (
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

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    oc_publication = report_publication_to_pydantic(report_publication)

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None
    assert len(oc_publication.cost_data.invoice) == 2

    invoice_numbers = {inv.invoice_number for inv in oc_publication.cost_data.invoice}
    assert "INV-2024-101" in invoice_numbers
    assert "INV-2024-102" in invoice_numbers


@pytest.mark.skip(reason="TODO: Implement contract/part_of_contract transformation")
@pytest.mark.django_db
def test__publication_with_contract__transforming_to_opencost__publication_cost_data_includes_contract() -> (
    None
):
    # TODO: Need to add contract data to OpenCostReportPublication model
    # TODO: Need to implement part_of_contract transformation
    pass

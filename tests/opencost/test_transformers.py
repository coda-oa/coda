from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from coda.apps.contracts.models import Contract, ContractLink, ContractLinkType
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportPublicationLink,
)
from coda.apps.opencost.transformers import (
    report_contract_to_pydantic,
    report_publication_to_pydantic,
    to_opencost,
)
from coda.apps.opencost.validation import ValidationWarning
from coda.apps.publications.models import Link, LinkType
from coda.apps.publications.models._attachedentities import PublicationAttachedConcept
from coda.apps.publications.models._vocabulary import Vocabulary
from coda.domain.contract import PublicationBilling
from opencost import (
    CoarPublicationType,
    ContractPrimaryIdentifierType,
    ContractSecondaryIdTypeEnum,
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
    generate_opencost_report_from_contract,
    transform_first_publication_to_pydantic,
)


@pytest.mark.django_db
def test__report_article_publication__transforming_to_opencost__returns_valid_opencost_publication() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Invoice Test Publication")
    fr.publication.online_publication_date = date(2024, 5, 15)
    # Remove DOI to test bibliographic_information path
    fr.publication.links.filter(type__name="DOI").delete()
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
    )

    result = transform_first_publication_to_pydantic()

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
    # Create funding request first, then convert to monograph
    fr = modelfactory.fundingrequest(title="Test Monograph")
    fr.publication.article_journal = None
    fr.publication.monograph_publisher = publisher
    # Remove DOI to test bibliographic_information path
    fr.publication.links.filter(type__name="DOI").delete()
    fr.publication.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-MONO-001",
        cost_amount=Decimal("2000.00"),
        cost_type="other",
    )

    result = transform_first_publication_to_pydantic()

    assert isinstance(result, PublicationType)
    assert result.primary_identifier.bibliographic_information is not None
    assert result.primary_identifier.bibliographic_information.Title == "Test Monograph"
    assert "Academic Press" in result.primary_identifier.bibliographic_information.Publisher


@pytest.mark.django_db
def test__report_publication_with_doi__transforming_to_opencost__doi_is_included_in_primary_identifier() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Test Publication with DOI")

    create_publication_with_invoice(
        publication=fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-DOI-001",
    )

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.primary_identifier.doi == "10.1234/5678"  # domainfactory default


@pytest.mark.django_db
def test__report_publication_with_publication_type__transforming_to_opencost__publication_type_is_included() -> (
    None
):
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

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.publication_type == CoarPublicationType.conference_paper


@pytest.mark.django_db
def test__report_publication_with_unmappable_publication_type__transforming_to_opencost__falls_back_to_other() -> (
    None
):
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

    oc_publication = transform_first_publication_to_pydantic()

    # CODA stores free vocabulary concept names; a name outside COAR must not
    # abort the export
    assert oc_publication.publication_type == CoarPublicationType.other


@pytest.mark.django_db
def test__report_publication_with_secondary_identifiers__transforming_to_opencost__secondary_identifiers_are_included() -> (
    None
):
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

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.secondary_identifiers is not None
    assert len(oc_publication.secondary_identifiers.id) == 3  # ISBN (factory) + Handle + URN

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
def test__report_publication_with_unmappable_link_type__transforming_to_opencost__link_is_excluded_from_secondary_identifiers() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with Web Link")

    url_type, _ = LinkType.objects.get_or_create(name="URL")
    Link.objects.create(
        publication=fr.publication,
        type=url_type,
        value="https://example.org/articles/4711",
    )

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(
        publication=fr.publication,
        type=handle_type,
        value="hdl:12345/9876",
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 20),
        invoice_number="INV-UNMAPPABLE-001",
    )

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.secondary_identifiers is not None
    values = [secondary_id.value for secondary_id in oc_publication.secondary_identifiers.id]

    assert "https://example.org/articles/4711" not in values
    assert "hdl:12345/9876" in values
    assert len(values) == 2  # ISBN (factory) + handle, the URL link is not an openCost type


@pytest.mark.django_db
def test__report_publication_with_only_unmappable_links__transforming_to_opencost__secondary_identifiers_are_omitted() -> (
    None
):
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

    oc_publication = transform_first_publication_to_pydantic()

    # openCost forbids an empty secondary_identifiers element, so the transformer
    # must omit it rather than emit id=[]
    assert oc_publication.secondary_identifiers is None


@pytest.mark.django_db
def test__report_publication_link_with_empty_value__transforming_to_opencost__link_is_excluded() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication With Empty Link Value")

    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(
        publication=fr.publication,
        type=handle_type,
        value="hdl:12345/9877",
    )

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 5, 22),
        invoice_number="INV-EMPTY-VALUE-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    # A snapshot row whose value is empty: openCost rejects it (NonEmptyString),
    # so the row must be dropped instead of failing the whole report
    OpenCostReportPublicationLink.objects.create(
        report_publication=report_publication,
        link_type="handle",
        value="",
    )

    oc_publication = report_publication_to_pydantic(report_publication)
    assert oc_publication is not None

    assert oc_publication.secondary_identifiers is not None
    values = [secondary_id.value for secondary_id in oc_publication.secondary_identifiers.id]

    assert "" not in values
    assert "hdl:12345/9877" in values
    assert len(values) == 2  # ISBN (factory) + handle, the empty row is dropped


@pytest.mark.django_db
def test__report_publication_with_institution_data__transforming_to_opencost__institution_data_is_included() -> (
    None
):
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

    oc_publication = transform_first_publication_to_pydantic()

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
def test__report_publication_with_unmappable_institution_identifier__transforming_to_opencost__identifier_is_excluded() -> (
    None
):
    institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/guard123",
    )

    fr = modelfactory.fundingrequest(title="Publication with bad institution identifiers")
    fr.publication.relevant_authors.all().delete()
    create_corresponding_author(publication=fr.publication, affiliation=institution)

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-INSTITUTION-GUARD-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    OpenCostReportInstitutionIdentifier.objects.create(
        report_publication=report_publication,
        identifier_type="otherid",
        value="https://example.org/no-identifier-scheme",
    )
    OpenCostReportInstitutionIdentifier.objects.create(
        report_publication=report_publication,
        identifier_type="isni",
        value="",
    )

    oc_publication = report_publication_to_pydantic(report_publication)
    assert oc_publication is not None

    assert oc_publication.institution.id is not None
    assert [(i.type, i.value) for i in oc_publication.institution.id] == [
        (InstitutionIdType.ror, "https://ror.org/guard123")
    ]


@pytest.mark.django_db
def test__report_contract_with_unmappable_institution_identifier__transforming_to_opencost__identifier_is_excluded() -> (
    None
):
    contract = create_contract_with_identifiers(name="Guard Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None

    OpenCostReportContractInstitutionIdentifier.objects.create(
        report_contract=report_contract,
        identifier_type="ror",
        value="https://ror.org/guard456",
    )
    OpenCostReportContractInstitutionIdentifier.objects.create(
        report_contract=report_contract,
        identifier_type="otherid",
        value="https://example.org/no-identifier-scheme",
    )
    OpenCostReportContractInstitutionIdentifier.objects.create(
        report_contract=report_contract,
        identifier_type="isni",
        value="",
    )

    opencost_data = to_opencost(report)
    assert opencost_data is not None
    assert opencost_data.contract is not None

    contract_data = opencost_data.contract[0]

    assert contract_data.institution.id is not None
    assert [(i.type, i.value) for i in contract_data.institution.id] == [
        (InstitutionIdType.ror, "https://ror.org/guard456")
    ]


@pytest.mark.django_db
def test__report_publication_with_invoice__transforming_to_opencost__cost_data_includes_invoice_with_correct_position_data() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with Invoice")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-001",
        creditor_name="Invoice Creditor",
        cost_amount=Decimal("1500.00"),
    )

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None

    invoice_data = oc_publication.cost_data.invoice[0]
    assert invoice_data.invoice_number == "INV-2024-001"
    assert invoice_data.creditor == "Invoice Creditor"

    assert invoice_data.dates.invoice == "2024-06-01"

    assert invoice_data.amount_invoice is not None
    assert invoice_data.amount_invoice.amount == Decimal("1500.00")
    assert invoice_data.amount_invoice.currency == "EUR"

    assert len(invoice_data.amounts_paid.amount_paid) == 1
    amount_paid = invoice_data.amounts_paid.amount_paid[0]
    assert amount_paid.amount == Decimal("1500.00")
    assert amount_paid.currency == "EUR"
    assert amount_paid.cost_type == PublicationCostType.gold_oa
    assert amount_paid.vat == Decimal("285.00")


@pytest.mark.django_db
def test__report_publication_with_invoice_multiple_positions__transforming_to_opencost__amount_invoice_and_amounts_paid_are_correct() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with Invoice and Multiple Positions")

    creditor = create_creditor(name="Invoice Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 6, 1), number="INV-2024-002"
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

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None

    invoice_data = oc_publication.cost_data.invoice[0]
    assert invoice_data.invoice_number == "INV-2024-002"

    assert invoice_data.amount_invoice is not None
    assert invoice_data.amount_invoice.amount == Decimal("1500.00")  # 1000 + 500
    assert invoice_data.amount_invoice.currency == "EUR"

    assert len(invoice_data.amounts_paid.amount_paid) == 2
    amounts = sorted(invoice_data.amounts_paid.amount_paid, key=lambda x: x.amount)
    assert amounts[0].amount == Decimal("500.00")
    assert amounts[1].amount == Decimal("1000.00")


@pytest.mark.django_db
def test__report_publication_with_multiple_invoices__transforming_to_opencost__all_invoices_are_included() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with Multiple Invoices")

    creditor1 = create_creditor(name="First Creditor")
    invoice1 = create_invoice(
        creditor=creditor1, invoice_date=date(2024, 5, 1), number="INV-2024-101"
    )
    create_position(
        invoice1,
        fr.publication,
        description="APC for test article - Invoice 1",
        cost_amount=Decimal("800.00"),
    )

    creditor2 = create_creditor(name="Second Creditor")
    invoice2 = create_invoice(
        creditor=creditor2, invoice_date=date(2024, 6, 1), number="INV-2024-102"
    )
    create_position(
        invoice2,
        fr.publication,
        description="APC for test article - Invoice 2",
        cost_amount=Decimal("700.00"),
    )

    oc_publication = transform_first_publication_to_pydantic()

    assert oc_publication.cost_data is not None
    assert oc_publication.cost_data.invoice is not None
    assert len(oc_publication.cost_data.invoice) == 2

    invoice_numbers = {inv.invoice_number for inv in oc_publication.cost_data.invoice}
    assert "INV-2024-101" in invoice_numbers
    assert "INV-2024-102" in invoice_numbers


@pytest.mark.django_db
def test__report_standalone_contract_with_institution_data__transforming_to_opencost__contract_data_is_included() -> (
    None
):
    report = OpenCostReport.objects.create(
        title="Test Report 2024",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )

    contract = modelfactory.contract()
    report_contract = OpenCostReportContract.objects.create(
        report=report,
        contract=contract,
        contract_name="Test Transform Agreement",
        institution_name="University of Testing",
        participation_from=date(2024, 1, 1),
        participation_to=date(2024, 12, 31),
        primary_identifier_value="",
    )

    OpenCostReportContractInstitutionIdentifier.objects.create(
        report_contract=report_contract,
        identifier_type="ror",
        value="https://ror.org/test123",
    )
    OpenCostReportContractInstitutionIdentifier.objects.create(
        report_contract=report_contract,
        identifier_type="isni",
        value="0000 0001 2345 6789",
    )

    creditor = create_creditor("Test Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 7, 1), number="INV-CONTRACT-001"
    )
    create_position(
        invoice=invoice,
        contract=contract,
        description="Service Fee",
        cost_amount=Decimal("1200.00"),
        cost_type="publish",
    )
    report_invoice = OpenCostReportContractInvoice.objects.create(
        report_contract=report_contract,
        invoice=invoice,
        invoice_number="INV-CONTRACT-001",
        creditor="Test Creditor",
        invoice_date=date(2024, 7, 1),
        amount_invoice=Decimal("1200.00"),
        amount_invoice_currency="EUR",
        group_id="test-group-id",
    )
    position = invoice.positions.first()
    assert position is not None
    OpenCostReportContractInvoicePosition.objects.create(
        report_contract_invoice=report_invoice,
        position=position,
        amount=Decimal("1200.00"),
        currency="EUR",
        cost_type="publish",
    )

    opencost_data = to_opencost(report)
    assert opencost_data is not None

    assert opencost_data.contract is not None
    assert len(opencost_data.contract) == 1

    contract_data = opencost_data.contract[0]

    assert contract_data.contract_name == "Test Transform Agreement"

    assert contract_data.institution is not None
    assert contract_data.institution.name is not None
    assert len(contract_data.institution.name) == 1
    assert contract_data.institution.name[0].value == "University of Testing"
    assert contract_data.institution.name[0].type == InstitutionNameType.full

    assert contract_data.institution.id is not None
    assert len(contract_data.institution.id) == 2

    ror_ids = [i for i in contract_data.institution.id if i.type == InstitutionIdType.ror]
    assert len(ror_ids) == 1
    assert ror_ids[0].value == "https://ror.org/test123"

    isni_ids = [i for i in contract_data.institution.id if i.type == InstitutionIdType.isni]
    assert len(isni_ids) == 1
    assert isni_ids[0].value == "0000 0001 2345 6789"

    assert contract_data.participation is not None
    assert contract_data.participation.from_ == "2024-01-01"
    assert contract_data.participation.to == "2024-12-31"


@pytest.mark.django_db
def test__report_standalone_contract_with_invoice_data__transforming_to_opencost__invoice_data_is_included() -> (
    None
):
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

    opencost_data = generate_opencost_report_from_contract()

    assert opencost_data.contract is not None

    contract_data = opencost_data.contract[0]

    assert contract_data.cost_data is not None
    assert contract_data.cost_data.invoice_group is not None

    opencost_invoice = contract_data.cost_data.invoice_group[0]

    assert opencost_invoice.invoice is not None
    assert len(opencost_invoice.invoice) == 1
    assert opencost_invoice.invoice[0].invoice_number == "INV-CONTRACT-001"
    assert opencost_invoice.invoice[0].creditor == "Contract Creditor"
    assert opencost_invoice.invoice[0].dates.invoice == "2024-07-01"
    assert opencost_invoice.invoice[0].amount_invoice is not None
    assert opencost_invoice.invoice[0].amount_invoice.amount == Decimal("1200.00")
    assert opencost_invoice.invoice[0].amount_invoice.currency == "EUR"

    assert opencost_invoice.invoices_period is not None
    assert opencost_invoice.invoices_period.from_ == "2024-01-01"
    assert opencost_invoice.invoices_period.to == "2024-12-31"


@pytest.mark.django_db
def test__report_standalone_contract_with_invoice_multiple_positions__transforming_to_opencost__amount_invoice_and_amounts_paid_are_correct() -> (
    None
):
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

    opencost_data = generate_opencost_report_from_contract()

    assert opencost_data.contract is not None
    contract_data = opencost_data.contract[0]

    opencost_invoice = contract_data.cost_data.invoice_group[0]

    assert opencost_invoice.invoice is not None
    assert opencost_invoice.invoice[0].amount_invoice is not None
    assert opencost_invoice.invoice[0].amount_invoice.amount == Decimal("1200.00")  # 700 + 500
    assert opencost_invoice.invoice[0].amount_invoice.currency == "EUR"

    assert len(opencost_invoice.invoice[0].amounts_paid.amount_paid) == 2
    amounts = sorted(opencost_invoice.invoice[0].amounts_paid.amount_paid, key=lambda x: x.amount)
    assert amounts[0].amount == Decimal("500.00")
    assert amounts[1].amount == Decimal("700.00")


@pytest.mark.django_db
def test__report_standalone_contract_with_esac_id__transforming_to_opencost__primary_identifier_value_is_set() -> (
    None
):
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
        number="INV-CONTRACT-002",
        status="paid",
    )

    create_position(
        invoice,
        contract=contract,
        description="Service Fee Part 1",
        cost_amount=Decimal("700.00"),
        cost_type="publish",
    )

    report = create_opencost_report(title="Test Report with Contract ESAC ID 2024")
    opencost_data = to_opencost(report)
    assert opencost_data is not None

    assert opencost_data.contract is not None
    contract_data = opencost_data.contract[0]

    contract_primary_id = contract_data.primary_identifier
    assert contract_primary_id is not None
    assert contract_primary_id.type == ContractPrimaryIdentifierType.ESAC
    assert contract_primary_id.value == "https://esac.org/id/123456"
    assert contract_primary_id.value != "https://otherid.com/id/555555"


@pytest.mark.django_db
def test__report_standalone_contract_with_secondary_identifiers__transforming_to_opencost__secondary_identifiers_are_included() -> (
    None
):
    contract = create_contract_with_identifiers(
        oai="https://services.dnb.de/oai/repository/789012",
        ezb="https://ezb.uni-regensburg.de/id/456789",
        local="LOCAL-ID-001",
    )

    invoice = create_invoice(
        creditor=create_creditor(name="Contract Creditor"),
        invoice_date=date(2024, 8, 1),
        number="INV-CONTRACT-002",
        status="paid",
    )

    create_position(
        invoice,
        contract=contract,
        description="Service Fee Part 1",
        cost_amount=Decimal("700.00"),
        cost_type="publish",
    )

    report = create_opencost_report(title="Test Report with Contract Secondary IDs 2024")
    opencost_data = to_opencost(report)
    assert opencost_data is not None

    assert opencost_data.contract is not None
    assert len(opencost_data.contract) == 1

    contract_data = opencost_data.contract[0]

    assert contract_data.secondary_identifiers is not None
    assert len(contract_data.secondary_identifiers.id) == 3

    oai_ids = [
        sid
        for sid in contract_data.secondary_identifiers.id
        if sid.type == ContractSecondaryIdTypeEnum.oai
    ]
    assert oai_ids[0].value == "https://services.dnb.de/oai/repository/789012"
    ezb_ids = [
        sid
        for sid in contract_data.secondary_identifiers.id
        if sid.type == ContractSecondaryIdTypeEnum.ezb
    ]
    assert ezb_ids[0].value == "https://ezb.uni-regensburg.de/id/456789"
    local_ids = [
        sid
        for sid in contract_data.secondary_identifiers.id
        if sid.type == ContractSecondaryIdTypeEnum.local
    ]
    assert local_ids[0].value == "LOCAL-ID-001"


@pytest.mark.django_db
def test__publication_with_linked_contract__transforming_to_opencost__attached_contract_is_included_in_report_publication() -> (
    None
):
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

    report = create_opencost_report()
    opencost_data = to_opencost(report)
    assert opencost_data is not None

    assert opencost_data.publication is not None
    assert len(opencost_data.publication) == 1

    publication_data = opencost_data.publication[0]

    assert publication_data.cost_data is not None
    assert publication_data.cost_data.invoice is not None
    assert len(publication_data.cost_data.invoice) == 1

    assert publication_data.cost_data.part_of_contract is not None
    assert publication_data.cost_data.part_of_contract.primary_identifier is not None
    assert (
        publication_data.cost_data.part_of_contract.primary_identifier.type
        == ContractPrimaryIdentifierType.ESAC
    )
    assert (
        publication_data.cost_data.part_of_contract.primary_identifier.value
        == "https://esac.org/id/test-contract-123"
    )


@pytest.mark.django_db
def test__report_invoice_without_date__transforming_to_opencost__invoice_is_excluded() -> None:
    fr = modelfactory.fundingrequest(title="Publication with undated invoice")

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-UNDATED-001",
    )
    invoice2 = create_invoice(
        creditor=create_creditor("Second Creditor"),
        invoice_date=date(2024, 6, 20),
        number="INV-UNDATED-002",
    )
    create_position(
        invoice2,
        fr.publication,
        description="APC for second invoice",
        cost_amount=Decimal("700.00"),
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None

    undated = report_publication.invoices.order_by("invoice_number").first()
    assert undated is not None
    undated.invoice_date = None
    undated.save()

    # openCost needs an invoice or payment date per invoice block, so the dated
    # invoice is reported and the undated one left out
    oc_publication = report_publication_to_pydantic(report_publication)
    assert oc_publication is not None
    assert oc_publication.cost_data.invoice is not None

    assert [invoice.invoice_number for invoice in oc_publication.cost_data.invoice] == [
        "INV-UNDATED-002"
    ]


@pytest.mark.django_db
def test__report_contract_without_participation_dates__transforming_to_opencost__contract_is_excluded() -> (
    None
):
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.participation_from = None
    report_contract.participation_to = None
    report_contract.save()

    # openCost requires both participation dates and the participation block
    # itself, so the contract cannot be reported at all
    assert to_opencost(report) is None


@pytest.mark.django_db
def test__report_contract_invoice_without_total__transforming_to_opencost__amount_invoice_is_omitted() -> (
    None
):
    contract = create_contract_with_identifiers(name="Totalless Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_invoice = report_contract.invoices.first()
    assert report_invoice is not None
    report_invoice.amount_invoice = None
    report_invoice.amount_invoice_currency = ""
    report_invoice.save()

    opencost_data = to_opencost(report)
    assert opencost_data is not None
    assert opencost_data.contract is not None

    invoice_group = opencost_data.contract[0].cost_data.invoice_group[0]
    assert invoice_group.invoice is not None

    invoice = invoice_group.invoice[0]
    assert invoice.invoice_number == "INV-CONTRACT-001"
    assert invoice.amount_invoice is None


@pytest.mark.django_db
def test__report_invoice_with_blank_text_fields__transforming_to_opencost__fields_are_omitted() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with blank invoice fields")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-BLANK-001",
        creditor_name="Blank Creditor",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None
    report_invoice.invoice_number = ""
    report_invoice.creditor = ""
    report_invoice.save()

    oc_publication = report_publication_to_pydantic(report_publication)
    assert oc_publication is not None
    assert oc_publication.cost_data.invoice is not None

    invoice = oc_publication.cost_data.invoice[0]
    assert invoice.invoice_number is None
    assert invoice.creditor is None
    assert invoice.amounts_paid.amount_paid[0].amount == Decimal("1500.00")


@pytest.mark.django_db
def test__report_invoice_position_with_unknown_cost_type__transforming_to_opencost__position_is_excluded() -> (
    None
):
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
        cost_type="other",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None

    positions = sorted(report_invoice.positions.all(), key=lambda position: position.amount)
    assert len(positions) == 2
    positions[0].cost_type = "apc"
    positions[0].save()

    oc_publication = report_publication_to_pydantic(report_publication)
    assert oc_publication is not None
    assert oc_publication.cost_data.invoice is not None

    amounts_paid = oc_publication.cost_data.invoice[0].amounts_paid.amount_paid
    assert len(amounts_paid) == 1
    assert amounts_paid[0].cost_type == PublicationCostType.gold_oa
    assert amounts_paid[0].amount == Decimal("1000.00")


@pytest.mark.django_db
def test__report_invoice_without_usable_positions__transforming_to_opencost__publication_is_excluded() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with only unmappable positions")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-COST-TYPE-002",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None

    position = report_invoice.positions.first()
    assert position is not None
    position.cost_type = "apc"
    position.save()

    # without a single reported amount the invoice block is empty, which openCost
    # forbids, and the publication then has no cost data at all
    assert report_publication_to_pydantic(report_publication) is None


@pytest.mark.django_db
def test__contract_without_participation_dates__transforming_to_opencost__exclusion_is_collected() -> (
    None
):
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.participation_from = None
    report_contract.save()

    excluded: list[ValidationWarning] = []

    assert to_opencost(report, excluded=excluded) is None

    assert len(excluded) == 1
    assert excluded[0].level == "error"
    assert excluded[0].entity_type == "contract"
    assert excluded[0].entity_name == "Undated Agreement"
    assert "participation" in excluded[0].message


@pytest.mark.django_db
def test__contract_invoice_without_date__transforming_to_opencost__exclusion_is_collected() -> None:
    contract = create_contract_with_identifiers(name="Undated Invoice Agreement")
    create_contract_with_invoice(contract, invoice_number="INV-NODATE-CONTRACT-001")

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_invoice = report_contract.invoices.first()
    assert report_invoice is not None
    report_invoice.invoice_date = None
    report_invoice.save()

    excluded: list[ValidationWarning] = []

    assert to_opencost(report, excluded=excluded) is None

    # the invoice and the contract both go, but a single entry tells the whole story
    assert len(excluded) == 1
    assert excluded[0].entity_type == "contract"
    assert "INV-NODATE-CONTRACT-001" in excluded[0].message
    assert "excluded entirely" in excluded[0].message


@pytest.mark.django_db
def test__report_invoice_without_date__transforming_to_opencost__exclusion_is_collected() -> None:
    fr = modelfactory.fundingrequest(title="Publication with an undated invoice")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-NODATE-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None
    report_invoice.invoice_date = None
    report_invoice.save()

    excluded: list[ValidationWarning] = []

    assert report_publication_to_pydantic(report_publication, excluded=excluded) is None

    assert len(excluded) == 1
    assert excluded[0].entity_type == "publication"
    assert excluded[0].entity_name == report_publication.title
    assert "INV-NODATE-001" in excluded[0].message
    assert "has no invoice date" in excluded[0].message


@pytest.mark.django_db
def test__invoice_position_with_unknown_cost_type__transforming_to_opencost__exclusion_is_collected() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with a partial invoice")
    invoice = create_invoice(
        creditor=create_creditor("Cost Type Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-COST-TYPE-003",
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

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None

    positions = sorted(report_invoice.positions.all(), key=lambda position: position.amount)
    positions[0].cost_type = "service fee"
    positions[0].save()

    excluded: list[ValidationWarning] = []

    assert report_publication_to_pydantic(report_publication, excluded=excluded) is not None

    assert len(excluded) == 1
    assert excluded[0].entity_type == "publication"
    assert "INV-COST-TYPE-003" in excluded[0].message
    assert "service fee" in excluded[0].message


@pytest.mark.django_db
def test__report_invoice_without_usable_positions__transforming_to_opencost__single_exclusion_is_collected() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with no reportable positions")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-COST-TYPE-004",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None

    position = report_invoice.positions.first()
    assert position is not None
    position.cost_type = "service fee"
    position.save()

    excluded: list[ValidationWarning] = []

    assert report_publication_to_pydantic(report_publication, excluded=excluded) is None

    assert len(excluded) == 1
    assert "excluded entirely" in excluded[0].message


@pytest.mark.django_db
def test__publication_without_institution__transforming_to_opencost__exclusion_is_collected() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication without institution data")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-NOINST-PUB-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_publication.institution_name = ""
    report_publication.save()
    report_publication.institution_identifiers.all().delete()

    excluded: list[ValidationWarning] = []

    assert report_publication_to_pydantic(report_publication, excluded=excluded) is None

    assert len(excluded) == 1
    assert excluded[0].entity_type == "publication"
    assert excluded[0].entity_name == report_publication.title
    assert "institution" in excluded[0].message


@pytest.mark.django_db
def test__contract_without_institution__transforming_to_opencost__exclusion_is_collected() -> None:
    contract = create_contract_with_identifiers(name="Agreement without institution data")
    create_contract_with_invoice(contract, invoice_number="INV-NOINST-CON-001")

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.institution_name = ""
    report_contract.save()
    report_contract.institution_identifiers.all().delete()

    excluded: list[ValidationWarning] = []

    assert report_contract_to_pydantic(report_contract, excluded=excluded) is None

    assert len(excluded) == 1
    assert excluded[0].entity_type == "contract"
    assert excluded[0].entity_name == report_contract.contract_name
    assert "institution" in excluded[0].message


@pytest.mark.django_db
def test__publication_exclusion__fix_url__links_to_the_funding_request() -> None:
    # A decoy publication first: the factories would otherwise allocate the publication and
    # the funding request the same primary key, hiding a wrong-id fix URL.
    modelfactory.publication(title="Decoy publication to desync identifiers")
    fr = modelfactory.fundingrequest(title="Publication whose exclusion links home")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-FIXURL-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.get(publication=fr.publication)
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None
    report_invoice.invoice_date = None
    report_invoice.save()

    excluded: list[ValidationWarning] = []

    assert report_publication_to_pydantic(report_publication, excluded=excluded) is None

    assert excluded[0].fix_url == reverse("fundingrequests:detail", kwargs={"pk": fr.pk})
    assert excluded[0].fix_url != reverse(
        "fundingrequests:detail", kwargs={"pk": report_publication.publication_id}
    )

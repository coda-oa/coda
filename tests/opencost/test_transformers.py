from datetime import date
from decimal import Decimal
import pytest

from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
)
from coda.apps.opencost.transformers import to_opencost
from coda.apps.publications.models._attachedentities import PublicationAttachedConcept
from coda.apps.publications.models._vocabulary import Vocabulary
from coda.domain.opencost._contract import (
    ContractPrimaryIdentifierType,
    ContractSecondaryIdTypeEnum,
)
from coda.domain.opencost._publication import PublicationSecondaryIdTypeEnum, PublicationType
from coda.domain.opencost._types import PublicationCostType
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
    transform_first_publication_to_pydantic,
    create_contract_with_invoice,
    generate_opencost_report_from_contract,
)
from coda.apps.publications.models import LinkType, Link
from coda.domain.opencost import CoarPublicationType

from coda.domain.opencost._institution import InstitutionIdType, InstitutionNameType

from coda.apps.contracts.models import Contract, ContractLink, ContractLinkType
from coda.domain.contract import PublicationBilling


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

    assert len(invoice_data.amounts_paid) == 2
    amounts = sorted(invoice_data.amounts_paid, key=lambda x: x.amount)
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

    opencost_data = to_opencost(report)

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

    assert len(opencost_invoice.invoice[0].amounts_paid) == 2
    amounts = sorted(opencost_invoice.invoice[0].amounts_paid, key=lambda x: x.amount)
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

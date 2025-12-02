from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from coda.apps.contracts.models import Contract
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from tests import modelfactory
from tests.opencost.helpers import (
    create_creditor,
    create_invoice,
    create_position,
    create_publication_with_invoice,
    create_opencost_report,
)
from coda.apps.opencost.xml_generation import generate_xml
from coda.apps.publications.models import LinkType, Link
from coda.apps.preferences.models import GlobalPreferences


@pytest.mark.django_db
def test__publication_with_all_info_and_invoice__generate_xml__creates_valid_opencost_xml() -> None:
    publication = modelfactory.publication(
        title="Test Publication with all Info and Invoice for XML Export"
    )
    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    Link.objects.create(publication=publication, type=doi_type, value="10.1234/test.doi")
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")
    Link.objects.create(publication=publication, type=handle_type, value="hdl:1234/5678")
    urn_type, _ = LinkType.objects.get_or_create(name="URN")
    Link.objects.create(publication=publication, type=urn_type, value="urn:nbn:de:1234-5678")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 20),
        invoice_number="INV-XML-001",
        creditor_name="XML Test Creditor",
        cost_amount=Decimal("1800.00"),
    )
    report = create_opencost_report()

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    # Debug: print the XML
    # print("\n" + xml_string)

    root = ET.fromstring(xml_string)

    ns = {"oc": "https://opencost.de"}

    assert root.tag == "{https://opencost.de}data"

    publications = root.findall("oc:publication", ns)
    assert len(publications) == 1

    pub = publications[0]
    doi_elem = pub.find("oc:primary_identifier/oc:doi", ns)
    assert doi_elem is not None
    assert doi_elem.text == "10.1234/test.doi"

    secondary_ids_elem = pub.find("oc:secondary_identifiers", ns)
    assert secondary_ids_elem is not None

    institution = pub.find("oc:institution", ns)
    assert institution is not None

    pub_type = pub.find("oc:publication_type", ns)
    assert pub_type is not None

    cost_data = pub.find("oc:cost_data", ns)
    assert cost_data is not None

    invoice = cost_data.find("oc:invoice", ns)
    assert invoice is not None

    invoice_number = invoice.find("oc:invoice_number", ns)
    assert invoice_number is not None
    assert invoice_number.text == "INV-XML-001"

    creditor = invoice.find("oc:creditor", ns)
    assert creditor is not None
    assert creditor.text == "XML Test Creditor"

    invoice_dates = invoice.find("oc:dates", ns)
    assert invoice_dates is not None

    invoice_date = invoice_dates.find("oc:invoice", ns)
    assert invoice_date is not None
    assert invoice_date.text == "2024-06-20"

    amount_invoice = invoice.find("oc:amount_invoice", ns)
    assert amount_invoice is not None
    amount_invoice_amount = amount_invoice.find("oc:amount", ns)
    assert amount_invoice_amount is not None
    assert amount_invoice_amount.text == "1800.0000"

    amounts_paid = invoice.find("oc:amounts_paid", ns)
    assert amounts_paid is not None
    amount_paid = amounts_paid.find("oc:amount_paid", ns)
    assert amount_paid is not None
    amount_paid_amount = amount_paid.find("oc:amount", ns)
    assert amount_paid_amount is not None
    assert amount_paid_amount.text == "1800.0000"
    amount_paid_currency = amount_paid.find("oc:currency", ns)
    assert amount_paid_currency is not None
    assert amount_paid_currency.text == "EUR"
    cost_type = amount_paid.find("oc:cost_type", ns)
    assert cost_type is not None
    assert cost_type.text == "gold-oa"
    vat = amount_paid.find("oc:vat", ns)
    assert vat is not None
    assert vat.text == "342.0000"


# Invoice with two Positions (amount paid)
@pytest.mark.django_db
def test__publication_with_invoice_multiple_positions__generate_xml__opencost_xml_has_right_amount() -> (
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

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    # Debug: print the XML
    # print("\n" + xml_string)

    root = ET.fromstring(xml_string)

    ns = {"oc": "https://opencost.de"}

    publications = root.findall("oc:publication", ns)
    pub = publications[0]
    cost_data = pub.find("oc:cost_data", ns)
    assert cost_data is not None

    xml_invoice = cost_data.find("oc:invoice", ns)
    assert xml_invoice is not None
    amount_invoice = xml_invoice.find("oc:amount_invoice", ns)
    assert amount_invoice is not None
    amount_invoice_amount = amount_invoice.find("oc:amount", ns)
    assert amount_invoice_amount is not None
    assert amount_invoice_amount.text == "1500.0000"


@pytest.mark.django_db
def test__publication_with_multiple_invoices__generate_xml__creates_valid_opencost_xml() -> None:
    publication = modelfactory.publication(title="Publication with Multiple Invoices")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 5),
        invoice_number="INV-MULTI-001",
        creditor_name="Multi Creditor 1",
        cost_amount=Decimal("800.00"),
    )
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-MULTI-002",
        creditor_name="Multi Creditor 2",
        cost_amount=Decimal("1200.00"),
    )

    report = create_opencost_report()

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    # Debug: print the XML
    # print("\n" + xml_string)

    root = ET.fromstring(xml_string)

    ns = {"oc": "https://opencost.de"}

    publications = root.findall("oc:publication", ns)
    pub = publications[0]
    cost_data = pub.find("oc:cost_data", ns)
    assert cost_data is not None

    invoices = cost_data.findall("oc:invoice", ns)
    assert len(invoices) == 2


# TODO: Publication with contract


@pytest.mark.django_db
def test__report_with_standalone_contract_with_institution__generate_xml__creates_valid_opencost_xml() -> (
    None
):
    home_institution = Institution.objects.create(name="Contract Test University")
    ror_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
    InstitutionLink.objects.create(
        institution=home_institution, type=ror_type, value="https://ror.org/contract123"
    )

    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    contract = Contract.objects.create(
        name="Standalone Contract for XML Test",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    creditor = create_creditor(name="Invoice Creditor")
    invoice = create_invoice(
        creditor=creditor, invoice_date=date(2024, 6, 1), number="INV-2024-002"
    )
    _contract_position = create_position(
        invoice,
        contract=contract,
        description="Service fee for contract",
        cost_amount=Decimal("2000.00"),
        cost_type="publish",
    )

    report = create_opencost_report(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    # Debug: print the XML
    # print("\n" + xml_string)

    root = ET.fromstring(xml_string)

    ns = {"oc": "https://opencost.de"}

    assert root.tag == "{https://opencost.de}data"

    contracts = root.findall("oc:contract", ns)
    assert len(contracts) == 1
    xml_contract = contracts[0]
    assert xml_contract is not None

    contract_name_elem = xml_contract.find("oc:contract_name", ns)
    assert contract_name_elem is not None
    assert contract_name_elem.text == "Standalone Contract for XML Test"

    institution = xml_contract.find("oc:institution", ns)
    assert institution is not None

    institution_name = institution.find("oc:name/oc:value", ns)
    assert institution_name is not None
    assert institution_name.text == "Contract Test University"

    institution_ids = institution.findall("oc:id", ns)
    assert len(institution_ids) == 1

    id_type = institution_ids[0].find("oc:type", ns)
    id_value = institution_ids[0].find("oc:value", ns)
    assert id_type is not None
    assert id_value is not None
    assert id_type.text == "ror"
    assert id_value.text == "https://ror.org/contract123"

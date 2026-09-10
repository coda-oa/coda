from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.xml_generation import generate_xml
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import Link, LinkType
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
    create_creditor,
    create_institution_with_identifiers,
    create_invoice,
    create_opencost_report,
    create_position,
    create_publication_with_invoice,
)


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
    assert amount_invoice_amount.text == "1800.00"

    amounts_paid = invoice.find("oc:amounts_paid", ns)
    assert amounts_paid is not None
    amount_paid = amounts_paid.find("oc:amount_paid", ns)
    assert amount_paid is not None
    amount_paid_amount = amount_paid.find("oc:amount", ns)
    assert amount_paid_amount is not None
    assert amount_paid_amount.text == "1800.00"
    amount_paid_currency = amount_paid.find("oc:currency", ns)
    assert amount_paid_currency is not None
    assert amount_paid_currency.text == "EUR"
    cost_type = amount_paid.find("oc:cost_type", ns)
    assert cost_type is not None
    assert cost_type.text == "gold-oa"
    vat = amount_paid.find("oc:vat", ns)
    assert vat is not None
    assert vat.text == "342.00"


# Invoice with two Positions (amount paid)
@pytest.mark.django_db
def test__publication_with_invoice_multiple_positions__generate_xml__opencost_xml_has_right_amount() -> (
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
    assert amount_invoice_amount.text == "1500.00"


@pytest.mark.django_db
def test__publication_with_multiple_invoices__generate_xml__creates_valid_opencost_xml() -> None:
    fr = modelfactory.fundingrequest(title="Publication with Multiple Invoices")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 5),
        invoice_number="INV-MULTI-001",
        creditor_name="Multi Creditor 1",
        cost_amount=Decimal("800.00"),
    )
    create_publication_with_invoice(
        fr.publication,
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


@pytest.mark.django_db
def test__publication_with_linked_contract__generate_xml__part_of_contract_is_included() -> None:
    # Create contract with ESAC identifier and invoice
    contract = create_contract_with_identifiers(
        name="Linked Contract for XML Test",
        esac="https://esac.org/id/test-contract-999",
    )

    # Add invoice to contract (needed for contract to be included)
    create_contract_with_invoice(
        contract,
        creditor_name="Contract Creditor",
        invoice_date=date(2024, 5, 1),
        invoice_number="INV-CONTRACT-999",
        position_descriptions=["Contract service fee"],
        position_amounts=[Decimal("5000.00")],
        cost_type="read",
    )

    # Create publication and link it to the contract
    fr = modelfactory.fundingrequest(title="Publication Linked to Contract")
    fr.publication.attached_contracts.create(contract=contract, contract_year=2024)

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-LINKED-001",
        creditor_name="Invoice Creditor",
        cost_amount=Decimal("1500.00"),
    )

    # A second publication attached to the same contract without its own
    # invoice: its cost data consists solely of the contract link
    fr_attached_only = modelfactory.fundingrequest(title="Attached Only Publication")
    fr_attached_only.publication.attached_contracts.create(contract=contract, contract_year=2024)

    report = create_opencost_report()

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    # Debug: print the XML
    # print("\n" + xml_string)

    root = ET.fromstring(xml_string)
    ns = {"oc": "https://opencost.de"}

    publications = root.findall("oc:publication", ns)
    assert len(publications) == 2

    pub = next(p for p in publications if p.find("oc:cost_data/oc:invoice", ns) is not None)
    cost_data = pub.find("oc:cost_data", ns)
    assert cost_data is not None

    invoice = cost_data.find("oc:invoice", ns)
    assert invoice is not None

    part_of_contract = cost_data.find("oc:part_of_contract", ns)
    assert part_of_contract is not None

    primary_id = part_of_contract.find("oc:primary_identifier", ns)
    assert primary_id is not None

    id_value = primary_id.find("oc:value", ns)
    assert id_value is not None
    assert id_value.text == "https://esac.org/id/test-contract-999"

    id_type = primary_id.find("oc:type", ns)
    assert id_type is not None
    assert id_type.text == "ESAC"

    part_of_contract_group_id = part_of_contract.find("oc:group_id", ns)
    assert part_of_contract_group_id is not None
    assert part_of_contract_group_id.text is not None
    assert len(part_of_contract_group_id.text) == 36

    attached_only = next(p for p in publications if p is not pub)
    attached_cost_data = attached_only.find("oc:cost_data", ns)
    assert attached_cost_data is not None
    # included without its own invoice: cost data is part_of_contract only
    assert attached_cost_data.findall("oc:invoice", ns) == []
    assert attached_cost_data.find("oc:part_of_contract", ns) is not None

    contracts = root.findall("oc:contract", ns)
    assert len(contracts) == 1

    contract_elem = contracts[0]
    contract_primary_id = contract_elem.find("oc:primary_identifier", ns)
    assert contract_primary_id is not None

    contract_id_value = contract_primary_id.find("oc:value", ns)
    assert contract_id_value is not None
    assert contract_id_value.text == "https://esac.org/id/test-contract-999"

    contract_cost_data = contract_elem.find("oc:cost_data", ns)
    assert contract_cost_data is not None

    invoice_group = contract_cost_data.find("oc:invoice_group", ns)
    assert invoice_group is not None

    contract_group_id = invoice_group.find("oc:group_id", ns)
    assert contract_group_id is not None
    assert contract_group_id.text == part_of_contract_group_id.text


@pytest.mark.django_db
def test__report_with_standalone_contract_with_institution__generate_xml__creates_valid_opencost_xml() -> (
    None
):
    home_institution = create_institution_with_identifiers(
        name="Contract Test University",
        ror="https://ror.org/contract123",
        isni="https://isni.org/contract123",
        ringold="RING-CONTRACT-123",
    )

    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    contract = create_contract_with_identifiers(
        name="Standalone Contract for XML Test",
        esac="https://esac.org/id/123456",
        oai="https://oai.org/id/123456",
        local="https://local.org/id/123456",
    )

    create_contract_with_invoice(
        contract,
        creditor_name="Invoice Creditor",
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-2024-002",
        position_descriptions=["Service fee for contract"],
        position_amounts=[Decimal("2000.00")],
        cost_type="publish",
    )

    report = create_opencost_report(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    # Debug: print the XML
    print("\n" + xml_string)

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

    ids = set()
    for id_elem in institution.findall("oc:id", ns):
        id_type = id_elem.find("oc:type", ns)
        id_value = id_elem.find("oc:value", ns)
        assert id_type is not None
        assert id_value is not None
        ids.add((id_type.text, id_value.text))
    assert ids == {
        ("ror", "https://ror.org/contract123"),
        ("isni", "https://isni.org/contract123"),
        ("ringold", "RING-CONTRACT-123"),
    }

    primary_id = xml_contract.find("oc:primary_identifier", ns)
    primary_id_type = primary_id.find("oc:type", ns) if primary_id is not None else None
    primary_id_value = primary_id.find("oc:value", ns) if primary_id is not None else None
    assert primary_id_type is not None
    assert primary_id_value is not None
    assert primary_id_value.text == "https://esac.org/id/123456"
    assert primary_id_type.text == "ESAC"

    secondary_ids = xml_contract.find("oc:secondary_identifiers", ns)
    assert secondary_ids is not None
    secondary_id_list = secondary_ids.findall("oc:id", ns)
    assert len(secondary_id_list) == 2

    cost_data = xml_contract.find("oc:cost_data", ns)
    assert cost_data is not None

    invoice_group = cost_data.find("oc:invoice_group", ns)
    assert invoice_group is not None

    invoices_period = invoice_group.find("oc:invoices_period", ns)
    assert invoices_period is not None

    period_from = invoices_period.find("oc:from", ns)
    period_to = invoices_period.find("oc:to", ns)
    assert period_from is not None
    assert period_to is not None
    assert period_from.text == "2024-01-01"
    assert period_to.text == "2024-12-31"


@pytest.mark.django_db
def test__report_publication_with_external_costsplitting__generate_xml__includes_external_costsplitting_element() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication with Cost Splitting")
    fr.external_costsplitting = True
    fr.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-SPLIT-001",
        creditor_name="Split Creditor",
        cost_amount=Decimal("1000.00"),
    )

    report = create_opencost_report()

    xml_string = generate_xml(report)

    assert xml_string is not None
    assert len(xml_string) > 0

    root = ET.fromstring(xml_string)
    ns = {"oc": "https://opencost.de"}

    publications = root.findall("oc:publication", ns)

    pub_with_splitting = publications[0]

    assert pub_with_splitting is not None
    external_costsplitting_elem = pub_with_splitting.find("oc:external_costsplitting", ns)
    assert external_costsplitting_elem is not None
    assert external_costsplitting_elem.text == "true"


@pytest.mark.django_db
def test__report_publication_without_external_costsplitting__generate_xml__costsplitting_element_is_omitted() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Publication without Cost Splitting")
    fr.external_costsplitting = None
    fr.save()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 8, 10),
        invoice_number="INV-No-Split-001",
        creditor_name="Creditor",
        cost_amount=Decimal("1200.00"),
    )

    report = create_opencost_report()

    xml_string = generate_xml(report)

    root = ET.fromstring(xml_string)
    ns = {"oc": "https://opencost.de"}

    publications = root.findall("oc:publication", ns)

    pub_without_cost_splitting = publications[0]
    external_costsplitting_elem = pub_without_cost_splitting.find("oc:external_costsplitting", ns)
    assert external_costsplitting_elem is None


@pytest.mark.django_db
def test__report_publication_without_doi__generate_xml__emits_bibliographic_information() -> None:
    fr = modelfactory.fundingrequest(title="Monograph Without DOI")
    # domainfactory always seeds a DOI link; removing it takes the
    # bibliographic_information branch of the primary_identifier choice
    fr.publication.links.filter(type__name="DOI").delete()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 7, 1),
        invoice_number="INV-NO-DOI-001",
        creditor_name="No DOI Creditor",
        cost_amount=Decimal("900.00"),
    )

    report = create_opencost_report()

    xml_string = generate_xml(report)

    root = ET.fromstring(xml_string)
    ns = {"oc": "https://opencost.de"}

    publications = root.findall("oc:publication", ns)
    assert len(publications) == 1
    primary_id = publications[0].find("oc:primary_identifier", ns)
    assert primary_id is not None
    assert primary_id.find("oc:doi", ns) is None

    bib_info = primary_id.find("oc:bibliographic_information", ns)
    assert bib_info is not None
    title_elem = bib_info.find("oc:Title", ns)
    publisher_elem = bib_info.find("oc:Publisher", ns)
    is_part_of_elem = bib_info.find("oc:isPartOf", ns)
    assert title_elem is not None
    assert publisher_elem is not None
    assert is_part_of_elem is not None
    journal = fr.publication.article_journal
    assert journal is not None
    assert title_elem.text == "Monograph Without DOI"
    assert publisher_elem.text == journal.publisher.name
    assert is_part_of_elem.text == journal.title


@pytest.mark.django_db
def test__generate_xml_with_unreportable_contract__collects_exclusion_reasons() -> None:
    publication = modelfactory.publication(title="Publication For Partial Export")
    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    Link.objects.create(publication=publication, type=doi_type, value="10.1234/partial.doi")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 20),
        invoice_number="INV-XML-EXCL-001",
    )
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.participation_to = None
    report_contract.save()

    excluded: list[ValidationWarning] = []

    xml_string = generate_xml(report, excluded=excluded)

    assert xml_string != ""
    assert "Undated Agreement" not in xml_string
    assert len(excluded) == 1
    assert excluded[0].entity_name == "Undated Agreement"

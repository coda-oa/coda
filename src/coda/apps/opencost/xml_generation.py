from xml.etree import ElementTree as ET

from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.transformers import report_publication_to_pydantic
from coda.domain.opencost import (
    PublicationType,
    PublicationPrimaryIdentifier,
    InstitutionType,
    PublicationCostDataType,
    PublicationInvoiceType,
    Data,
)


def pydantic_to_xml(data: Data) -> str:
    root = ET.Element("data", xmlns="https://opencost.de")

    if data.publication:
        for pub in data.publication:
            pub_elem = serialize_publication(pub)
            root.append(pub_elem)

    # Serialize contracts (TODO)
    if data.contract:
        for contract in data.contract:
            # TODO: Implement contract serialization
            pass

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    xml_string = ET.tostring(root, encoding="unicode")

    return xml_string


def serialize_publication(pub: PublicationType) -> ET.Element:
    pub_elem = ET.Element("publication")

    primary_id_elem = serialize_primary_identifier(pub.primary_identifier)
    pub_elem.append(primary_id_elem)

    if pub.secondary_identifiers:
        secondary_ids_elem = ET.SubElement(pub_elem, "secondary_identifiers")
        for sec_id in pub.secondary_identifiers.id:
            sec_id_elem = ET.SubElement(secondary_ids_elem, "id")

            value_elem = ET.SubElement(sec_id_elem, "value")
            value_elem.text = sec_id.value

            type_elem = ET.SubElement(sec_id_elem, "type")
            type_elem.text = sec_id.type.value

    institution_elem = serialize_institution(pub.institution)
    pub_elem.append(institution_elem)

    pub_type_elem = ET.SubElement(pub_elem, "publication_type")
    pub_type_elem.text = pub.publication_type.value

    if pub.external_costsplitting is not None:
        cost_split_elem = ET.SubElement(pub_elem, "external_costsplitting")
        cost_split_elem.text = str(pub.external_costsplitting).lower()

    cost_data_elem = serialize_publication_cost_data(pub.cost_data)
    pub_elem.append(cost_data_elem)

    return pub_elem


def serialize_primary_identifier(primary_id: PublicationPrimaryIdentifier) -> ET.Element:
    primary_id_elem = ET.Element("primary_identifier")

    if primary_id.doi:
        doi_elem = ET.SubElement(primary_id_elem, "doi")
        doi_elem.text = primary_id.doi
    elif primary_id.bibliographic_information:
        bib_info_elem = ET.SubElement(primary_id_elem, "bibliographic_information")

        title_elem = ET.SubElement(bib_info_elem, "Title")
        title_elem.text = primary_id.bibliographic_information.Title

        publisher_elem = ET.SubElement(bib_info_elem, "Publisher")
        publisher_elem.text = primary_id.bibliographic_information.Publisher

        is_part_of_elem = ET.SubElement(bib_info_elem, "isPartOf")
        is_part_of_elem.text = primary_id.bibliographic_information.isPartOf

    return primary_id_elem


def serialize_institution(institution: InstitutionType) -> ET.Element:
    institution_elem = ET.Element("institution")

    if institution.name:
        for name in institution.name:
            name_elem = ET.SubElement(institution_elem, "name")

            value_elem = ET.SubElement(name_elem, "value")
            value_elem.text = name.value

            type_elem = ET.SubElement(name_elem, "type")
            type_elem.text = name.type.value  # "full" or "short"

    if institution.id:
        for inst_id in institution.id:
            id_elem = ET.SubElement(institution_elem, "id")

            value_elem = ET.SubElement(id_elem, "value")
            value_elem.text = inst_id.value

            type_elem = ET.SubElement(id_elem, "type")
            type_elem.text = inst_id.type.value  # "ror", "isni", or "ringold"

    return institution_elem


def serialize_publication_cost_data(cost_data: PublicationCostDataType) -> ET.Element:
    cost_data_elem = ET.Element("cost_data")

    if cost_data.invoice:
        for invoice in cost_data.invoice:
            invoice_elem = serialize_publication_invoice(invoice)
            cost_data_elem.append(invoice_elem)

    if cost_data.part_of_contract:
        # TODO: Implement part_of_contract serialization
        pass

    return cost_data_elem


def serialize_publication_invoice(invoice: PublicationInvoiceType) -> ET.Element:
    invoice_elem = ET.Element("invoice")

    if invoice.invoice_number:
        invoice_number_elem = ET.SubElement(invoice_elem, "invoice_number")
        invoice_number_elem.text = invoice.invoice_number

    if invoice.creditor:
        creditor_elem = ET.SubElement(invoice_elem, "creditor")
        creditor_elem.text = invoice.creditor

    dates_elem = ET.SubElement(invoice_elem, "dates")

    if invoice.dates.invoice:
        invoice_date_elem = ET.SubElement(dates_elem, "invoice")
        invoice_date_elem.text = invoice.dates.invoice

    if invoice.dates.paid:
        paid_date_elem = ET.SubElement(dates_elem, "paid")
        paid_date_elem.text = invoice.dates.paid

    if invoice.amount_invoice:
        amount_invoice_elem = ET.SubElement(invoice_elem, "amount_invoice")

        currency_elem = ET.SubElement(amount_invoice_elem, "currency")
        currency_elem.text = invoice.amount_invoice.currency

        amount_elem = ET.SubElement(amount_invoice_elem, "amount")
        amount_elem.text = str(invoice.amount_invoice.amount)

    amounts_paid_elem = ET.SubElement(invoice_elem, "amounts_paid")
    for amount_paid in invoice.amounts_paid:
        amount_paid_elem_position = ET.SubElement(amounts_paid_elem, "amount_paid")

        amount_elem = ET.SubElement(amount_paid_elem_position, "amount")
        amount_elem.text = str(amount_paid.amount)

        currency_elem = ET.SubElement(amount_paid_elem_position, "currency")
        currency_elem.text = amount_paid.currency

        cost_type_elem = ET.SubElement(amount_paid_elem_position, "cost_type")
        cost_type_elem.text = amount_paid.cost_type.value

        if amount_paid.vat is not None:
            vat_elem = ET.SubElement(amount_paid_elem_position, "vat")
            vat_elem.text = str(amount_paid.vat)

    return invoice_elem


def generate_xml(report: OpenCostReport) -> str:
    pydantic_publications = []
    for report_pub in report.publications.all():
        pydantic_pub = report_publication_to_pydantic(report_pub)
        pydantic_publications.append(pydantic_pub)

    data = Data(
        publication=pydantic_publications if pydantic_publications else None,
        contract=None,  # TODO: Add contract support
    )
    xml_string = pydantic_to_xml(data)

    return xml_string

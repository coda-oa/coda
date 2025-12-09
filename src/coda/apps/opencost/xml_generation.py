from xml.etree import ElementTree as ET

from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.transformers import to_opencost
from coda.domain.opencost import (
    PublicationType,
    PublicationPrimaryIdentifier,
    InstitutionType,
    PublicationCostDataType,
    PublicationInvoiceType,
    Data,
)
from coda.domain.opencost._contract import (
    ContractType,
    ParticipationType,
    ContractPrimaryIdentifier,
)
from coda.domain.opencost._invoice import (
    ContractCostDataType,
    ContractInvoiceGroupType,
    ContractInvoiceType,
)


def pydantic_to_xml(data: Data) -> str:
    root = ET.Element("data", xmlns="https://opencost.de")

    if data.publication:
        for pub in data.publication:
            pub_elem = serialize_publication(pub)
            root.append(pub_elem)

    # Serialize contracts
    if data.contract:
        for contract in data.contract:
            contract_elem = serialize_contract(contract)
            root.append(contract_elem)

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
        part_of_contract_elem = ET.SubElement(cost_data_elem, "part_of_contract")

        if cost_data.part_of_contract.group_id:
            group_id_elem = ET.SubElement(part_of_contract_elem, "group_id")
            group_id_elem.text = cost_data.part_of_contract.group_id

        primary_id_elem = ET.SubElement(part_of_contract_elem, "primary_identifier")

        value_elem = ET.SubElement(primary_id_elem, "value")
        value_elem.text = cost_data.part_of_contract.primary_identifier.value

        type_elem = ET.SubElement(primary_id_elem, "type")
        type_elem.text = cost_data.part_of_contract.primary_identifier.type.value

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


def serialize_contract(contract: ContractType) -> ET.Element:
    contract_elem = ET.Element("contract")

    contract_name_elem = ET.SubElement(contract_elem, "contract_name")
    contract_name_elem.text = contract.contract_name

    institution_elem = serialize_institution(contract.institution)
    contract_elem.append(institution_elem)

    participation_elem = serialize_participation(contract.participation)
    contract_elem.append(participation_elem)

    primary_id_elem = serialize_contract_primary_identifier(contract.primary_identifier)
    contract_elem.append(primary_id_elem)

    if contract.secondary_identifiers:
        secondary_ids_elem = ET.SubElement(contract_elem, "secondary_identifiers")
        for sec_id in contract.secondary_identifiers.id:
            sec_id_elem = ET.SubElement(secondary_ids_elem, "id")

            value_elem = ET.SubElement(sec_id_elem, "value")
            value_elem.text = sec_id.value

            type_elem = ET.SubElement(sec_id_elem, "type")
            type_elem.text = sec_id.type.value

    cost_data_elem = serialize_contract_cost_data(contract.cost_data)
    contract_elem.append(cost_data_elem)

    return contract_elem


def serialize_participation(participation: ParticipationType) -> ET.Element:
    participation_elem = ET.Element("participation")

    from_elem = ET.SubElement(participation_elem, "from")
    from_elem.text = participation.from_

    to_elem = ET.SubElement(participation_elem, "to")
    to_elem.text = participation.to

    return participation_elem


def serialize_contract_primary_identifier(
    primary_id: ContractPrimaryIdentifier,
) -> ET.Element:
    primary_id_elem = ET.Element("primary_identifier")

    value_elem = ET.SubElement(primary_id_elem, "value")
    value_elem.text = primary_id.value

    type_elem = ET.SubElement(primary_id_elem, "type")
    type_elem.text = primary_id.type.value

    return primary_id_elem


def serialize_contract_cost_data(cost_data: ContractCostDataType) -> ET.Element:
    cost_data_elem = ET.Element("cost_data")

    for invoice_group in cost_data.invoice_group:
        invoice_group_elem = serialize_contract_invoice_group(invoice_group)
        cost_data_elem.append(invoice_group_elem)

    return cost_data_elem


def serialize_contract_invoice_group(
    invoice_group: ContractInvoiceGroupType,
) -> ET.Element:
    invoice_group_elem = ET.Element("invoice_group")

    if invoice_group.group_id:
        group_id_elem = ET.SubElement(invoice_group_elem, "group_id")
        group_id_elem.text = invoice_group.group_id

    if invoice_group.invoices_period:
        period_elem = ET.SubElement(invoice_group_elem, "invoices_period")

        from_elem = ET.SubElement(period_elem, "from")
        from_elem.text = invoice_group.invoices_period.from_

        to_elem = ET.SubElement(period_elem, "to")
        to_elem.text = invoice_group.invoices_period.to

    if invoice_group.invoice:
        for invoice in invoice_group.invoice:
            invoice_elem = serialize_contract_invoice(invoice)
            invoice_group_elem.append(invoice_elem)

    return invoice_group_elem


def serialize_contract_invoice(invoice: ContractInvoiceType) -> ET.Element:
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
    data = to_opencost(report)
    xml_string = pydantic_to_xml(data)
    return xml_string

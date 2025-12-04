from decimal import Decimal
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportPublication,
)
from coda.domain.opencost import Data
from coda.domain.opencost._contract import (
    ContractPrimaryIdentifier,
    ContractPrimaryIdentifierType,
    ContractSecondaryIdentifiersType,
    ContractSecondaryIdType,
    ContractSecondaryIdTypeEnum,
    ContractType,
    ParticipationType,
)
from coda.domain.opencost._institution import (
    InstitutionId,
    InstitutionIdType,
    InstitutionName,
    InstitutionNameType,
    InstitutionType,
)
from coda.domain.opencost._invoice import (
    AmountInvoice,
    ContractAmountPaidType,
    ContractCostDataType,
    ContractInvoiceGroupType,
    ContractInvoiceType,
    Dates,
    PublicationAmountPaidType,
    PublicationInvoiceType,
)
from coda.domain.opencost._publication import (
    BibliographicInformation,
    CoarPublicationType,
    PublicationCostDataType,
    PublicationPrimaryIdentifier,
    PublicationSecondaryIdType,
    PublicationSecondaryIdTypeEnum,
    PublicationSecondaryIdentifiers,
    PublicationType,
)


def report_publication_to_pydantic(report_pub: OpenCostReportPublication) -> PublicationType:
    if report_pub.doi:
        primary_identifier = PublicationPrimaryIdentifier(doi=report_pub.doi)
    else:
        bib_info = BibliographicInformation(
            Title=report_pub.title,
            Publisher=report_pub.publisher or "Unknown Publisher",
            isPartOf=report_pub.journal if report_pub.journal else "N/A",
        )
        primary_identifier = PublicationPrimaryIdentifier(bibliographic_information=bib_info)

    secondary_identifiers = _get_secondary_identifiers(report_pub)

    institution = _get_institution(report_pub)

    publication_type = _get_publication_type(report_pub)

    invoice_data = _get_invoice_data(report_pub)

    # TODO: Build cost_data (contracts) - TODO: Add contract transformation

    cost_data = PublicationCostDataType(invoice=invoice_data, part_of_contract=None)

    publication = PublicationType(
        primary_identifier=primary_identifier,
        secondary_identifiers=secondary_identifiers,
        institution=institution,
        publication_type=publication_type,
        external_costsplitting=report_pub.external_costsplitting,
        cost_data=cost_data,
    )

    return publication


def _get_publication_type(report_pub: OpenCostReportPublication) -> CoarPublicationType:
    if report_pub.publication_type:
        try:
            return CoarPublicationType(report_pub.publication_type)
        except ValueError:
            pass
    return CoarPublicationType.other


def _get_secondary_identifiers(
    report_pub: OpenCostReportPublication,
) -> PublicationSecondaryIdentifiers | None:
    secondary_ids: list[PublicationSecondaryIdType] = []

    for link in report_pub.links.all():
        try:
            id_type = PublicationSecondaryIdTypeEnum(link.link_type)
            secondary_ids.append(PublicationSecondaryIdType(value=link.value, type=id_type))
        except ValueError:
            continue

    if not secondary_ids:
        return None

    return PublicationSecondaryIdentifiers(id=secondary_ids)


def _get_invoice_data(report_pub: OpenCostReportPublication) -> list[PublicationInvoiceType] | None:
    report_invoices = report_pub.invoices.all()

    if not report_invoices:
        return None

    invoice_list = []
    for report_invoice in report_invoices:
        report_positions = report_invoice.positions.all()

        if not report_positions:
            continue

        amounts_paid = []
        for report_position in report_positions:
            amounts_paid.append(
                PublicationAmountPaidType(
                    amount=report_position.amount,
                    currency=report_position.currency,
                    cost_type=report_position.cost_type,
                    vat=report_position.vat or Decimal("0"),
                )
            )

        dates = Dates(
            invoice=str(report_invoice.invoice_date) if report_invoice.invoice_date else None,
            paid=None,
        )

        total_amount = sum(pos.amount for pos in report_positions)
        currency = report_positions[0].currency if report_positions else None
        amount_invoice = AmountInvoice(amount=total_amount, currency=currency)

        invoice_list.append(
            PublicationInvoiceType(
                invoice_number=report_invoice.invoice_number,
                creditor=report_invoice.creditor,
                amounts_paid=amounts_paid,
                dates=dates,
                amount_invoice=amount_invoice,
            )
        )

    return invoice_list if invoice_list else None


def _get_institution(report_pub: OpenCostReportPublication) -> InstitutionType:
    names = []
    if report_pub.institution_name:
        names.append(
            InstitutionName(value=report_pub.institution_name, type=InstitutionNameType.full)
        )

    identifiers = []
    for inst_id in report_pub.institution_identifiers.all():
        try:
            id_type = InstitutionIdType(inst_id.identifier_type)
            identifiers.append(InstitutionId(value=inst_id.value, type=id_type))
        except ValueError:
            continue

    return InstitutionType(
        name=names if names else None,
        id=identifiers if identifiers else None,
    )


def to_opencost(report: OpenCostReport) -> Data:
    publications = [
        report_publication_to_pydantic(report_pub) for report_pub in report.publications.all()
    ]

    contracts = [
        report_contract_to_pydantic(report_contract) for report_contract in report.contracts.all()
    ]

    return Data(
        publication=publications if publications else None,
        contract=contracts if contracts else None,
    )


def report_contract_to_pydantic(report_contract: OpenCostReportContract) -> ContractType:
    institution = _get_contract_institution(report_contract)

    participation = ParticipationType(
        **{
            "from": str(report_contract.participation_from)
            if report_contract.participation_from
            else None,
            "to": str(report_contract.participation_to)
            if report_contract.participation_to
            else None,
        }
    )

    primary_identifier = ContractPrimaryIdentifier(
        value=report_contract.primary_identifier_value or "UNKNOWN",
        type=ContractPrimaryIdentifierType.ESAC,
    )

    contract_secondary_identifiers = _get_contract_secondary_identifiers(report_contract)

    cost_data = _get_contract_cost_data(report_contract)

    return ContractType(
        contract_name=report_contract.contract_name,
        institution=institution,
        participation=participation,
        primary_identifier=primary_identifier,
        secondary_identifiers=contract_secondary_identifiers,
        cost_data=cost_data,
    )


def _get_contract_institution(report_contract: OpenCostReportContract) -> InstitutionType:
    names = []
    if report_contract.institution_name:
        names.append(
            InstitutionName(value=report_contract.institution_name, type=InstitutionNameType.full)
        )

    identifiers = []
    for inst_id in report_contract.institution_identifiers.all():
        try:
            id_type = InstitutionIdType(inst_id.identifier_type)
            identifiers.append(InstitutionId(value=inst_id.value, type=id_type))
        except ValueError:
            continue

    return InstitutionType(
        name=names if names else None,
        id=identifiers if identifiers else None,
    )


def _get_contract_cost_data(report_contract: OpenCostReportContract) -> ContractCostDataType:
    report_invoices = report_contract.invoices.all()

    if not report_invoices:
        return ContractCostDataType(invoice_group=[])

    invoice_list = []
    for report_invoice in report_invoices:
        report_positions = report_invoice.positions.all()

        if not report_positions:
            continue

        amounts_paid = []
        for report_position in report_positions:
            amounts_paid.append(
                ContractAmountPaidType(
                    amount=report_position.amount,
                    currency=report_position.currency,
                    cost_type=report_position.cost_type,
                    vat=report_position.vat or Decimal("0"),
                )
            )

        dates = Dates(
            invoice=str(report_invoice.invoice_date) if report_invoice.invoice_date else None,
            paid=None,
        )

        amount_invoice = AmountInvoice(
            amount=report_invoice.amount_invoice,
            currency=report_invoice.amount_invoice_currency,
        )

        invoice_list.append(
            ContractInvoiceType(
                invoice_number=report_invoice.invoice_number,
                creditor=report_invoice.creditor,
                amounts_paid=amounts_paid,
                dates=dates,
                amount_invoice=amount_invoice,
            )
        )

    # TODO: Implement grouping logic
    # For now, create a single invoice group with all invoices
    # In the future, we might group by period or other criteria
    invoice_group = ContractInvoiceGroupType(
        group_id=None,  # TODO grouping identifier
        invoices_period=None,  # TODO period specification
        invoice=invoice_list if invoice_list else None,
    )

    return ContractCostDataType(invoice_group=[invoice_group])


def _get_contract_secondary_identifiers(
    report_contract: OpenCostReportContract,
) -> ContractSecondaryIdentifiersType | None:
    secondary_ids: list[ContractSecondaryIdType] = []

    for identifier in report_contract.secondary_identifiers.all():
        try:
            id_type = ContractSecondaryIdTypeEnum(identifier.identifier_type)
            secondary_ids.append(ContractSecondaryIdType(value=identifier.value, type=id_type))
        except ValueError:
            continue

    if not secondary_ids:
        return None

    return ContractSecondaryIdentifiersType(id=secondary_ids)

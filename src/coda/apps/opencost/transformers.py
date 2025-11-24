from decimal import Decimal
from coda.apps.opencost.models import OpenCostReportPublication
from coda.domain.opencost._institution import InstitutionName, InstitutionNameType, InstitutionType
from coda.domain.opencost._invoice import (
    AmountInvoice,
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

    # TODO: Build institution from snapshot (we'll need to add institution_name to snapshot model)
    # For now, use institution name as placeholder
    institution = InstitutionType(
        name=[InstitutionName(value="Placeholder Institution", type=InstitutionNameType.full)],
        id=None,
    )

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

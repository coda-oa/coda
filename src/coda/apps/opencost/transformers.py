from coda.domain.opencost import (
    PublicationType,
    PublicationPrimaryIdentifier,
    BibliographicInformation,
    CoarPublicationType,
    PublicationCostDataType,
    InstitutionType,
    PublicationSecondaryIdentifiers,
    PublicationSecondaryIdType,
    PublicationSecondaryIdTypeEnum,
    PublicationInvoiceType,
)
from coda.apps.publications.models import Publication as PublicationModel
from coda.domain.opencost._contract import ContractPrimaryIdentifier, ContractPrimaryIdentifierType
from coda.domain.opencost._invoice import AmountInvoice, PublicationAmountPaidType, Dates
from decimal import Decimal
from coda.apps.invoices.models import Position
from coda.domain.opencost._publication import PartOfContractType


def to_publication(publication_data: PublicationModel) -> PublicationType:
    doi_value = _get_doi(publication_data)

    primary_identifier = PublicationPrimaryIdentifier(
        doi=doi_value,
        bibliographic_information=BibliographicInformation(
            Title=publication_data.title or "Unknown Title",
            Publisher=_get_publisher_name(publication_data),
            isPartOf=_get_journal_name(publication_data),
        ),
    )

    secondary_identifiers = _get_secondary_identifiers(publication_data)

    institution = InstitutionType(name=None, id=None)  # DUMMY

    publication_type = _get_publication_type(publication_data)

    # external cost splitting still missing

    invoice_data = _get_invoice_data(publication_data)

    # contract data - returns dummy data still
    contract_data = _get_contract_data(publication_data)

    cost_data = PublicationCostDataType(invoice=invoice_data, part_of_contract=contract_data)

    return PublicationType(
        primary_identifier=primary_identifier,
        secondary_identifiers=secondary_identifiers,
        institution=institution,
        publication_type=publication_type,
        external_costsplitting=False,  # DUMMY
        cost_data=cost_data,
    )


def _get_doi(publication: PublicationModel) -> str | None:
    for link in publication.links.all():
        if link.type.name.lower() == "doi":
            return link.value
    return None


def _get_publisher_name(publication: PublicationModel) -> str:
    if publication.monograph_publisher:
        return str(publication.monograph_publisher.name)
    if publication.article_journal and getattr(publication.article_journal, "publisher", None):
        return str(publication.article_journal.publisher.name)
    return "Unknown Publisher"


def _get_journal_name(publication: PublicationModel) -> str:
    if publication.article_journal:
        return str(publication.article_journal.title)
    return "Unknown Journal"


def _get_publication_type(publication: PublicationModel) -> CoarPublicationType:
    if publication.publication_type:
        try:
            return CoarPublicationType(publication.publication_type.name)
        except ValueError:
            pass
    return CoarPublicationType.other  # Default fallback


def _get_secondary_identifiers(
    publication: PublicationModel,
) -> PublicationSecondaryIdentifiers | None:
    secondary_ids: list[PublicationSecondaryIdType] = []

    for link in publication.links.all():
        link_type_name = link.type.name.lower()

        if link_type_name == "doi":
            continue

        try:
            id_type = PublicationSecondaryIdTypeEnum(link_type_name)
            secondary_ids.append(PublicationSecondaryIdType(value=link.value, type=id_type))
        except ValueError:
            continue

    if not secondary_ids:
        return None

    return PublicationSecondaryIdentifiers(id=secondary_ids)


def _get_invoice_data(publication: PublicationModel) -> list[PublicationInvoiceType] | None:
    invoices_dict: dict[int, list[Position]] = {}
    for position in publication.position_set.all():
        invoice_id = position.invoice.id
        if invoice_id not in invoices_dict:
            invoices_dict[invoice_id] = []
        invoices_dict[invoice_id].append(position)

    if not invoices_dict:
        return None

    invoice_list = []
    for invoice_id, positions in invoices_dict.items():
        invoice = positions[0].invoice

        amounts_paid = []
        for position in positions:
            try:
                cost_type = position.cost_type
            except (ValueError, AttributeError):
                cost_type = "other"

            amounts_paid.append(
                PublicationAmountPaidType(
                    amount=Decimal(str(position.cost_amount)),
                    currency=position.cost_currency,
                    cost_type=cost_type,
                    vat=Decimal(str(position.cost_amount))
                    * (Decimal(str(position.tax_rate)) if position.tax_rate else Decimal("0")),
                )
            )

        dates = Dates(invoice=str(invoice.date) if invoice.date else None, paid=None)

        total_amount = sum(position.cost_amount for position in positions)
        currency = positions[0].cost_currency if positions else None
        amount_invoice = AmountInvoice(amount=total_amount, currency=currency)

        invoice_list.append(
            PublicationInvoiceType(
                invoice_number=invoice.number,
                creditor=invoice.creditor.name,
                amounts_paid=amounts_paid,
                dates=dates,
                amount_invoice=amount_invoice,
            )
        )

    return invoice_list if invoice_list else None


# Still DUMMY
def _get_contract_data(publication: PublicationModel) -> PartOfContractType | None:
    return PartOfContractType(
        group_id=None,
        primary_identifier=ContractPrimaryIdentifier(
            value="DUMMY-ESAC-VALUE", type=ContractPrimaryIdentifierType.ESAC
        ),
    )

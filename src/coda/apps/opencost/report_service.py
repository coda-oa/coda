from datetime import date
from decimal import Decimal
from coda.apps.invoices.models import Position
from coda.apps.opencost.data_aggregation import get_publications_for_period
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
    OpenCostReportInvoice,
    OpenCostReportPublicationLink,
)
from coda.apps.publications.models import Publication
from coda.apps.preferences.models import GlobalPreferences


def generate_report(title: str, period_start: date, period_end: date) -> OpenCostReport:
    report = OpenCostReport.objects.create(
        title=title, period_start=period_start, period_end=period_end
    )

    publications = get_publications_for_period(
        start_date=period_start,
        end_date=period_end,
    )

    for publication in publications:
        doi_link = publication.links.filter(type__name="DOI").first()
        doi_value = doi_link.value if doi_link else ""

        if publication.article_journal:
            publisher_name = publication.article_journal.publisher.name
            journal_name = publication.article_journal.title
        elif publication.monograph_publisher:
            publisher_name = publication.monograph_publisher.name
            journal_name = ""
        else:
            publisher_name = ""
            journal_name = ""

        pub_type_name = publication.publication_type.name if publication.publication_type else ""

        institution_name, institution_identifiers = _get_institution_data(publication)

        report_publication = OpenCostReportPublication.objects.create(
            report=report,
            publication=publication,
            title=publication.title,
            doi=doi_value,
            publication_type=pub_type_name,
            publisher=publisher_name,
            journal=journal_name,
            external_costsplitting=None,  # Will implement with cost sharing later
            institution_name=institution_name,
        )

        for identifier_type, identifier_value in institution_identifiers:
            OpenCostReportInstitutionIdentifier.objects.create(
                report_publication=report_publication,
                identifier_type=identifier_type,
                value=identifier_value,
            )

        for link in publication.links.all():
            link_type_name = link.type.name.lower()
            if link_type_name == "doi":
                continue

            OpenCostReportPublicationLink.objects.create(
                report_publication=report_publication,
                link_type=link_type_name,
                value=link.value,
            )

        invoices_dict: dict[int, list[Position]] = {}
        for position in publication.position_set.all():
            invoice = position.invoice

            if invoice.date and period_start <= invoice.date <= period_end:
                invoice_id = invoice.id
                if invoice_id not in invoices_dict:
                    invoices_dict[invoice_id] = []
                invoices_dict[invoice_id].append(position)

        for invoice_id, positions in invoices_dict.items():
            invoice = positions[0].invoice

            report_invoice = OpenCostReportInvoice.objects.create(
                report_publication=report_publication,
                invoice=invoice,
                invoice_number=invoice.number or "",
                creditor=invoice.creditor.name if invoice.creditor else "",
                invoice_date=invoice.date,
            )

            for position in positions:
                OpenCostReportInvoicePosition.objects.create(
                    report_invoice=report_invoice,
                    position=position,
                    amount=position.cost_amount,
                    currency=position.cost_currency,
                    cost_type=position.cost_type,
                    vat=Decimal(str(position.cost_amount))
                    * (Decimal(str(position.tax_rate)) if position.tax_rate else Decimal("0")),
                )

    return report


def _get_institution_data(publication: Publication) -> tuple[str, list[tuple[str, str]]]:
    corresponding_author = publication.relevant_authors.filter(
        roles__contains="CORRESPONDING_AUTHOR"
    ).first()

    if corresponding_author and corresponding_author.affiliation:
        institution = corresponding_author.affiliation
        institution_name = institution.name

        identifiers = []
        for link in institution.links.filter(type__name__in=["ROR", "ISNI", "Ringold"]):
            identifier_type = link.type.name.lower()
            identifiers.append((identifier_type, link.value))

        if identifiers:
            return institution_name, identifiers

    home_identifier = GlobalPreferences.get_home_institution_identifier()

    if home_identifier:
        identifier_lower = home_identifier.lower()
        if "ror.org" in identifier_lower:
            identifier_type = "ror"
        elif "isni" in identifier_lower or " " in home_identifier:
            identifier_type = "isni"
        else:
            identifier_type = "ringold"

        return "Home Institution", [(identifier_type, home_identifier)]

    return "", []

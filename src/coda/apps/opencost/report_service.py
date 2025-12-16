import uuid
from datetime import date
from decimal import Decimal
from coda.apps.contracts.models import Contract
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Position
from coda.apps.opencost.data_aggregation import (
    get_publications_for_period,
    get_contracts_for_period,
)
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportContractSecondaryIdentifier,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
    OpenCostReportPublicationContract,
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
        _snapshot_publication(report, publication)

    contracts = get_contracts_for_period(
        start_date=period_start,
        end_date=period_end,
    )

    for contract in contracts:
        _snapshot_contract(report, contract)

    _update_publication_contract_group_ids(report)

    return report


def _update_publication_contract_group_ids(report: OpenCostReport) -> None:
    for pub_contract_link in OpenCostReportPublicationContract.objects.filter(
        report_publication__report=report
    ):
        report_contract = report.contracts.filter(contract=pub_contract_link.contract).first()

        if report_contract:
            first_invoice = report_contract.invoices.first()
            if first_invoice and first_invoice.group_id:
                pub_contract_link.group_id = first_invoice.group_id
                pub_contract_link.save()


def _snapshot_publication(
    report: OpenCostReport,
    publication: Publication,
) -> None:
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
        external_costsplitting=publication.external_costsplitting,
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

    for attached in publication.attached_contracts.all():
        OpenCostReportPublicationContract.objects.create(
            report_publication=report_publication,
            contract=attached.contract,
            contract_year=attached.contract_year,
            group_id="",  # Optional, can be set later if needed
        )

    _snapshot_publication_invoices(report_publication, publication)


def _snapshot_publication_invoices(
    report_publication: OpenCostReportPublication,
    publication: Publication,
) -> None:
    invoices_dict: dict[int, list[Position]] = {}
    for position in publication.position_set.all():
        invoice = position.invoice
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


def _snapshot_contract(
    report: OpenCostReport,
    contract: Contract,
) -> None:
    institution_name, institution_identifiers = _get_home_institution_data()
    primary_id = _get_contract_primary_identifier(contract)

    report_contract = OpenCostReportContract.objects.create(
        report=report,
        contract=contract,
        contract_name=contract.name,
        institution_name=institution_name,
        participation_from=contract.start_date,
        participation_to=contract.end_date,
        primary_identifier_value=primary_id,
    )

    for identifier_type, identifier_value in institution_identifiers:
        OpenCostReportContractInstitutionIdentifier.objects.create(
            report_contract=report_contract,
            identifier_type=identifier_type,
            value=identifier_value,
        )

    contract_identifiers = _get_contract_secondary_identifiers(contract)
    for identifier_type, identifier_value in contract_identifiers:
        OpenCostReportContractSecondaryIdentifier.objects.create(
            report_contract=report_contract,
            identifier_type=identifier_type,
            value=identifier_value,
        )

    group_id = str(uuid.uuid4())
    _snapshot_contract_invoices(report_contract, contract, group_id)


def _snapshot_contract_invoices(
    report_contract: OpenCostReportContract,
    contract: Contract,
    group_id: str,
) -> None:
    contract_invoices_dict: dict[int, list[Position]] = {}
    for position in contract.position_set.all():
        invoice = position.invoice
        invoice_id = invoice.id
        if invoice_id not in contract_invoices_dict:
            contract_invoices_dict[invoice_id] = []
        contract_invoices_dict[invoice_id].append(position)

    for invoice_id, positions in contract_invoices_dict.items():
        invoice = positions[0].invoice

        total_amount = sum(Decimal(str(p.cost_amount)) for p in positions)
        currency = positions[0].cost_currency if positions else ""

        report_contract_invoice = OpenCostReportContractInvoice.objects.create(
            report_contract=report_contract,
            invoice=invoice,
            invoice_number=invoice.number or "",
            creditor=invoice.creditor.name if invoice.creditor else "",
            invoice_date=invoice.date,
            amount_invoice=total_amount,
            amount_invoice_currency=currency,
            group_id=group_id,
        )

        for position in positions:
            OpenCostReportContractInvoicePosition.objects.create(
                report_contract_invoice=report_contract_invoice,
                position=position,
                amount=position.cost_amount,
                currency=position.cost_currency,
                cost_type=position.cost_type,
                vat=Decimal(str(position.cost_amount))
                * (Decimal(str(position.tax_rate)) if position.tax_rate else Decimal("0")),
            )


def _get_institution_data(publication: Publication) -> tuple[str, list[tuple[str, str]]]:
    corresponding_author = publication.relevant_authors.filter(
        roles__contains="CORRESPONDING_AUTHOR"
    ).first()

    if corresponding_author and corresponding_author.affiliation:
        current_institution: Institution | None = corresponding_author.affiliation

        while current_institution:
            institution_name = current_institution.name
            identifiers = []

            for link in current_institution.links.filter(type__name__in=["ROR", "ISNI", "Ringold"]):
                identifier_type = link.type.name.lower()
                identifiers.append((identifier_type, link.value))

            if identifiers:
                return institution_name, identifiers

            current_institution = current_institution.parent

    return _get_home_institution_data()


def _get_home_institution_data() -> tuple[str, list[tuple[str, str]]]:
    prefs = GlobalPreferences.objects.first()
    if not prefs or not prefs.home_institution:
        return "", []

    institution = prefs.home_institution
    institution_name = institution.name

    identifiers = []
    for link in institution.links.filter(type__name__in=["ROR", "ISNI", "Ringold"]):
        identifier_type = link.type.name.lower()
        identifiers.append((identifier_type, link.value))

    return institution_name, identifiers


def _get_contract_primary_identifier(contract: Contract) -> str:
    esac = contract.links.filter(type__name="ESAC").first()
    if esac:
        return esac.value
    return ""


def _get_contract_secondary_identifiers(contract: Contract) -> list[tuple[str, str]]:
    identifiers = []
    for link in contract.links.filter(type__name__in=["OAI", "EZB", "Local"]):
        identifier_type = link.type.name.lower()
        identifiers.append((identifier_type, link.value))
    return identifiers

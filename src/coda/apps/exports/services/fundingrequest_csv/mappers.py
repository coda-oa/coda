from coda.apps.exports.services.fundingrequest_csv.dtos import FundingRequestExportDto
from datetime import date

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice, Position, FundingAssignment
from coda.contexts.fundingrequest.dto.import_dtos import (
    AuthorImportDto,
    ContractImportDto,
    ConceptImportDto,
    CostEstimateImportDto,
    FundingRequestImportDto,
    LinkImportDto,
    PublicationImportDto,
    PublishingStateImportDto,
    ResearchFundingImportDto,
    ReviewImportDto,
    DecidedFundingImportDto,
    SeperateContactImportDto,
)
from coda.contexts.finance.dto.import_dtos import (
    InvoiceImportDto,
    PublicationPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
    FundingAssignmentImportDto,
    ConversionImportDto,
)
from coda.domain.author import Role
from coda.domain.orcid import Orcid
from coda.domain.publication import License, OpenAccessType
from coda.domain.finance.costtypes import PublicationCostType, ContractCostType
from coda.domain.finance.invoice import PaymentStatus, FundingSourceId
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.fundingrequest import PaymentMethod


def map_funding_request_to_dto(funding_request: FundingRequest) -> FundingRequestImportDto:
    publication = _map_publication_to_dto(funding_request)
    research_funding = _map_external_funding_to_dto(funding_request)
    review = _map_review_to_dto(funding_request)
    estimated_cost = _map_estimated_cost_to_dto(funding_request)
    seperate_contact = _map_seperate_contact_to_dto(funding_request)
    labels = _map_labels_to_dto(funding_request)
    request_id = str(funding_request.request_id) if funding_request.request_id else None

    return FundingRequestImportDto(
        request_date=funding_request.request_date,
        legacy_request_id=funding_request.legacy_request_id,
        publication=publication,
        research_funding=research_funding,
        review=review,
        estimated_cost=estimated_cost,
        request_remarks=funding_request.request_remarks or "",
        seperate_contact=seperate_contact,
        labels=labels,
        request_id=request_id,
    )


def _map_publication_to_dto(funding_request: FundingRequest) -> PublicationImportDto:
    # Determine if article or monograph
    journal = funding_request.publication.article_journal
    is_article = journal is not None

    # Get journal/publisher names
    if is_article:
        assert journal is not None  # Type narrowing for mypy
        eissn = journal.eissn
        journal_name = journal.title
        publisher_name = journal.publisher.name
    else:
        eissn = ""
        journal_name = "Imported nameless journal"
        publisher_name = (
            funding_request.publication.monograph_publisher.name
            if funding_request.publication.monograph_publisher
            else "Imported nameless publisher"
        )

    # Map authors
    authors = [
        AuthorImportDto(
            name=author.name,
            email=author.email or "",
            orcid=(
                Orcid(author.identifier.orcid)
                if author.identifier and author.identifier.orcid
                else None
            ),
            affiliation=author.affiliation.name if author.affiliation else None,
            role=Role[author.roles] if author.roles else Role.CO_AUTHOR,
        )
        for author in funding_request.publication.relevant_authors.all()
    ]

    # Map links
    links = [
        LinkImportDto(type=link.type.name, value=link.value)
        for link in funding_request.publication.links.all()
    ]

    # Map contracts
    contracts = [
        ContractImportDto(name=attached.contract.name, year=attached.contract_year)
        for attached in funding_request.publication.attached_contracts.all()
    ]

    # Map subject area
    subject_area = ConceptImportDto(
        name=(
            funding_request.publication.subject_area.name
            if funding_request.publication.subject_area
            else ""
        ),
        vocabulary_name=(
            funding_request.publication.subject_area.vocabulary.name
            if funding_request.publication.subject_area
            and funding_request.publication.subject_area.vocabulary
            else ""
        ),
    )

    # Map publication type
    publication_type = ConceptImportDto(
        name=(
            funding_request.publication.publication_type.name
            if funding_request.publication.publication_type
            else ""
        ),
        vocabulary_name=(
            funding_request.publication.publication_type.vocabulary.name
            if funding_request.publication.publication_type
            and funding_request.publication.publication_type.vocabulary
            else ""
        ),
    )

    # Map publishing state
    publishing_state = PublishingStateImportDto(
        state=(
            "published"
            if funding_request.publication.publication_state == "Published"
            else funding_request.publication.publication_state.lower()
        ),
        online_date=funding_request.publication.online_publication_date,
        print_date=funding_request.publication.print_publication_date,
    )

    publication = PublicationImportDto(
        title=funding_request.publication.title,
        open_access_type=OpenAccessType[funding_request.publication.open_access_type],
        kind="article" if is_article else "monograph",
        eissn=eissn,
        journal_name=journal_name,
        publisher_name=publisher_name,
        authors=authors,
        license=License[funding_request.publication.license],
        publishing_state=publishing_state,
        links=links,
        contracts=contracts,
        subject_area=subject_area,
        publication_type=publication_type,
    )

    return publication


def _map_external_funding_to_dto(funding_request: FundingRequest) -> list[ResearchFundingImportDto]:
    research_funding = [
        ResearchFundingImportDto(
            funder=external_funding.organization.name if external_funding.organization else "",
            project_id=external_funding.project_id,
            project_name=external_funding.project_name,
        )
        for external_funding in funding_request.external_funding.all()
    ]

    return research_funding


def _map_review_to_dto(funding_request: FundingRequest) -> ReviewImportDto:
    review_model = getattr(funding_request, "review", None)
    if review_model:

        decided_funding = DecidedFundingImportDto(
            amount=(
                review_model.decided_funding_amount if review_model.decided_funding_amount else 0
            ),
            currency=review_model.decided_funding_currency or "EUR",
        )
        # ReviewResult values are stored in lowercase in DB, but enum names are capitalized
        review_result_str = (
            review_model.review_result.capitalize() if review_model.review_result else "Open"
        )
        return ReviewImportDto(
            result=ReviewResult[review_result_str],
            funding=decided_funding,
            remarks=review_model.remarks or "",
        )
    return ReviewImportDto()


def _map_estimated_cost_to_dto(funding_request: FundingRequest) -> CostEstimateImportDto:

    # PaymentMethod values are stored in lowercase in DB, but enum names are capitalized
    payment_method_str = (
        funding_request.payment_method.capitalize() if funding_request.payment_method else "Unknown"
    )
    return CostEstimateImportDto(
        amount=funding_request.estimated_cost,
        currency=funding_request.estimated_cost_currency,
        payment_method=PaymentMethod[payment_method_str],
    )


def _map_seperate_contact_to_dto(funding_request: FundingRequest) -> SeperateContactImportDto:
    if funding_request.extra_contact:
        return SeperateContactImportDto(
            name=funding_request.extra_contact.name, email=funding_request.extra_contact.email
        )
    return SeperateContactImportDto.default()


def _map_labels_to_dto(funding_request: FundingRequest) -> list[str]:
    return [label.name for label in funding_request.labels.all()]


def map_invoice_to_dto(invoice: Invoice) -> InvoiceImportDto:
    currency = "EUR"
    if invoice.positions.exists():
        first_position = invoice.positions.first()
        if first_position:
            currency = first_position.cost_currency

    conversion = None
    if invoice.currency_conversions.exists():
        conv = invoice.currency_conversions.first()
        if conv:
            conversion = ConversionImportDto(
                target_currency=conv.target_currency, exchange_rate=conv.exchange_rate
            )

    positions = [_map_position_to_dto(pos) for pos in invoice.positions.all()]

    return InvoiceImportDto(
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor.name,
        currency=currency,
        status=PaymentStatus[invoice.status.capitalize()],
        external_id=invoice.external_invoice_id or "",
        comment=invoice.comment or "",
        conversion=conversion,
        positions=positions,
    )


def _map_position_to_dto(
    position: Position,
) -> PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto:
    """Map Django Position model to appropriate position DTO based on type.

    Position type is determined by what's set:
    - publication → PublicationPositionImportDto
    - contract → ContractPositionImportDto
    - neither → FreePositionImportDto
    """
    # Map funding assignments (common to all types)
    funding_assignments = [
        _map_funding_assignment_to_dto(fa) for fa in position.funding_assignments.all()
    ]

    # Get funding source from first assignment if exists
    funding_source = ""
    if funding_assignments:
        funding_source = funding_assignments[0].name

    # Common fields
    common_kwargs = {
        "amount": position.cost_amount,
        "tax_rate": position.tax_rate * 100,  # Convert from fraction to percentage
        "funding_source": funding_source,
        "external_id": position.external_position_id or "",
        "funding_assignments": funding_assignments,
    }

    # Determine position type and create appropriate DTO
    if position.publication is not None:
        funding_request = FundingRequest.objects.filter(publication=position.publication).first()

        request_id = str(funding_request.request_id) if funding_request else None
        legacy_request_id = funding_request.legacy_request_id if funding_request else ""

        return PublicationPositionImportDto(
            type="publication",
            request_id=request_id,
            legacy_request_id=legacy_request_id,
            cost_type=PublicationCostType(position.cost_type),
            **common_kwargs,
        )

    elif position.contract is not None:
        # Contract position
        return ContractPositionImportDto(
            type="contract",
            contract_name=position.contract.name,
            contract_year=position.contract_year or 0,
            cost_type=ContractCostType(position.cost_type),
            **common_kwargs,
        )

    else:
        return FreePositionImportDto(
            type="free",
            description=position.description or "",
            cost_type=PublicationCostType(position.cost_type),
            **common_kwargs,
        )


def _map_funding_assignment_to_dto(assignment: FundingAssignment) -> FundingAssignmentImportDto:
    funding_source = assignment.funding_source

    return FundingAssignmentImportDto(
        type=funding_source.type if funding_source else "budget",
        name=funding_source.name if funding_source else "",
        amount=assignment.amount,
    )


def map_funding_request_to_export_dto(
    funding_request: FundingRequest,
    invoice_date_start: date | None = None,
    invoice_date_end: date | None = None,
    invoice_status: str | None = None,
    invoice_creditor: str = "",
    funding_source: FundingSourceId | None = None,
) -> FundingRequestExportDto:

    funding_request_dto = map_funding_request_to_dto(funding_request)

    invoices_qs = Invoice.objects.filter(positions__publication=funding_request.publication)

    if invoice_date_start and invoice_date_end:
        invoices_qs = invoices_qs.filter(
            date__gte=invoice_date_start,
            date__lte=invoice_date_end,
        )
    if invoice_status:
        invoices_qs = invoices_qs.filter(status=invoice_status)
    if invoice_creditor:
        invoices_qs = invoices_qs.filter(creditor__name__icontains=invoice_creditor)
    if funding_source:
        invoices_qs = invoices_qs.filter(
            positions__funding_assignments__funding_source=funding_source,
        )

    invoices_qs = invoices_qs.distinct()

    invoice_dtos = [map_invoice_to_dto(invoice) for invoice in invoices_qs]

    return FundingRequestExportDto(
        funding_request=funding_request_dto,
        invoices=invoice_dtos,
    )

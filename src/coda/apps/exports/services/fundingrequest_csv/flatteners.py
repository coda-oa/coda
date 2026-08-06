from dataclasses import dataclass
from decimal import Decimal

from coda.apps.exports.services.fundingrequest_csv.dtos import FundingRequestExportDto
from coda.contexts.finance.dto.import_dtos import (
    InvoiceImportDto,
    PublicationPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
    FundingAssignmentImportDto,
)
from coda.contexts.fundingrequest.dto.import_dtos import (
    FundingRequestImportDto,
    AuthorImportDto,
    LinkImportDto,
    ResearchFundingImportDto,
    PublishingStateImportDto,
    ReviewImportDto,
    CostEstimateImportDto,
)


def flatten_detailed(dto: FundingRequestExportDto) -> list[dict[str, str]]:
    rows = []

    if not dto.invoices:
        rows.append(_create_row(dto.funding_request))
        return rows

    for invoice in dto.invoices:
        for position in invoice.positions:

            if not position.funding_assignments:
                rows.append(
                    _create_row(
                        funding_request=dto.funding_request,
                        invoice=invoice,
                        position=position,
                        funded_amount=position.amount,
                    )
                )
                continue

            for assignment in position.funding_assignments:
                rows.append(
                    _create_row(
                        funding_request=dto.funding_request,
                        invoice=invoice,
                        position=position,
                        assignment=assignment,
                        funded_amount=assignment.amount or Decimal("0"),
                    )
                )

    return rows


def _create_base_row(
    funding_request: FundingRequestImportDto,
) -> dict[str, str]:

    pub = funding_request.publication
    cost = funding_request.estimated_cost
    review = funding_request.review

    pub_state = _get_publishing_state_dates(pub.publishing_state)
    review_info = _get_review_info(review)
    cost_info = _get_cost_info(cost)
    funding_info = _get_research_funding(funding_request.research_funding)
    identifiers = _get_identifiers(pub.links)

    return {
        "legacy_request_id": funding_request.legacy_request_id or "",
        "request_date": funding_request.request_date.isoformat(),
        "publication_title": pub.title,
        "publication_kind": pub.kind,
        "eissn": pub.eissn or "",
        "journal_name": pub.journal_name,
        "publisher_name": pub.publisher_name,
        "license": pub.license.value,
        "open_access_type": pub.open_access_type.value,
        "authors": _format_authors(pub.authors),
        "doi": identifiers.doi,
        "isbn": identifiers.isbn,
        "handle": identifiers.handle,
        "publishing_state": pub_state.state,
        "online_date": pub_state.online_date,
        "print_date": pub_state.print_date,
        "subject_area": pub.subject_area.name or "",
        "publication_type": pub.publication_type.name or "",
        "estimated_amount": cost_info.amount,
        "estimated_currency": cost_info.currency,
        "payment_method": cost_info.payment_method,
        "review_result": review_info.result,
        "review_remarks": review_info.remarks,
        "decided_funding_amount": review_info.decided_amount,
        "decided_funding_currency": review_info.decided_currency,
        "labels": "; ".join(funding_request.labels),
        "project_id": funding_info.project_id,
        "project_name": funding_info.project_name,
        "funding_organization": funding_info.funder,
        "contract_name": _format_contract_names(funding_request),
        "contract_year": _format_contract_years(funding_request),
        "request_id": funding_request.request_id or "",
    }


def _create_row(
    funding_request: FundingRequestImportDto,
    invoice: InvoiceImportDto | None = None,
    position: (
        PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto | None
    ) = None,
    assignment: FundingAssignmentImportDto | None = None,
    funded_amount: Decimal | None = None,
) -> dict[str, str]:

    row = _create_base_row(funding_request)

    row.update(
        {
            "invoice_number": (invoice.number if invoice else ""),
            "invoice_date": (invoice.date.isoformat() if invoice else ""),
            "creditor": (invoice.creditor if invoice else ""),
            "invoice_status": (invoice.status.value if invoice else ""),
            "invoice_currency": (invoice.currency if invoice else ""),
            "invoice_comment": (invoice.comment if invoice else ""),
            "external_invoice_id": (invoice.external_id if invoice else ""),
            "position_amount": (str(position.amount) if position else ""),
            "tax_rate": (str(position.tax_rate) if position else ""),
            "cost_type": (position.cost_type.value if position else ""),
            "funded_amount": (str(funded_amount) if funded_amount is not None else ""),
            "funding_source_name": (assignment.name if assignment else ""),
            "funding_source_type": (assignment.type if assignment else ""),
        }
    )

    if position:
        row.update(_get_position_specific_fields(position))
    else:
        row.update(
            {
                "position_type": "",
                "legacy_position_request_id": "",
                "position_description": "",
            }
        )

    return row


def _format_authors(
    authors: list[AuthorImportDto],
) -> str:
    return "; ".join(author.name for author in authors if author.name)


def _get_position_specific_fields(
    position: PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto,
) -> dict[str, str]:
    if isinstance(position, PublicationPositionImportDto):
        return {
            "position_type": "publication",
            "legacy_position_request_id": position.legacy_request_id or "",
            "position_description": "",
        }
    elif isinstance(position, ContractPositionImportDto):
        return {
            "position_type": "contract",
            "legacy_position_request_id": "",
            "contract_name": position.contract_name,
            "contract_year": str(position.contract_year),
            "position_description": "",
        }
    else:  # FreePositionImportDto
        return {
            "position_type": "free",
            "legacy_position_request_id": "",
            "position_description": position.description,
        }


def _extract_identifier(links: list[LinkImportDto], identifier_type: str) -> str:
    for link in links:
        if link.type.lower() == identifier_type.lower():
            return str(link.value)
    return ""


def _format_contract_names(funding_request: FundingRequestImportDto) -> str:
    if not funding_request.publication.contracts:
        return ""

    return "; ".join(contract.name for contract in funding_request.publication.contracts)


def _format_contract_years(funding_request: FundingRequestImportDto) -> str:
    if not funding_request.publication.contracts:
        return ""

    return "; ".join(str(contract.year) for contract in funding_request.publication.contracts)


@dataclass(frozen=True)
class PublishingStateInfo:
    state: str
    online_date: str
    print_date: str


def _get_publishing_state_dates(publishing_state: PublishingStateImportDto) -> PublishingStateInfo:
    """Return PublishingStateInfo from a publishing state DTO."""
    state = getattr(publishing_state, "state", None) or ""
    online = getattr(publishing_state, "online_date", None)
    online_str = online.isoformat() if online else ""
    print_d = getattr(publishing_state, "print_date", None)
    print_str = print_d.isoformat() if print_d else ""
    return PublishingStateInfo(state=state, online_date=online_str, print_date=print_str)


@dataclass(frozen=True)
class ReviewInfo:
    result: str
    remarks: str
    decided_amount: str
    decided_currency: str


def _get_review_info(review: ReviewImportDto) -> ReviewInfo:
    """Return ReviewInfo from a review DTO."""
    result = getattr(review, "result", None)
    result_str = result.value if result else ""
    remarks = getattr(review, "remarks", None) or ""
    funding = getattr(review, "funding", None)
    amount = str(funding.amount) if funding else ""
    currency = funding.currency if funding else ""
    return ReviewInfo(
        result=result_str, remarks=remarks, decided_amount=amount, decided_currency=currency
    )


@dataclass(frozen=True)
class CostInfo:
    amount: str
    currency: str
    payment_method: str


def _get_cost_info(estimated_cost: CostEstimateImportDto) -> CostInfo:
    """Return CostInfo from an estimated cost DTO."""
    amount_str = str(getattr(estimated_cost, "amount", ""))
    currency = getattr(estimated_cost, "currency", "") or ""
    payment = getattr(estimated_cost, "payment_method", None)
    payment_str = payment.value if payment else ""
    return CostInfo(amount=amount_str, currency=currency, payment_method=payment_str)


@dataclass(frozen=True)
class ResearchFundingInfo:
    project_id: str
    project_name: str
    funder: str


def _get_research_funding(research_funding: list[ResearchFundingImportDto]) -> ResearchFundingInfo:
    """Return ResearchFundingInfo from first research funding entry."""
    if not research_funding:
        return ResearchFundingInfo(project_id="", project_name="", funder="")
    rf = research_funding[0]
    return ResearchFundingInfo(
        project_id=getattr(rf, "project_id", "") or "",
        project_name=getattr(rf, "project_name", "") or "",
        funder=getattr(rf, "funder", "") or "",
    )


@dataclass(frozen=True)
class IdentifierInfo:
    doi: str
    isbn: str
    handle: str


def _get_identifiers(links: list[LinkImportDto]) -> IdentifierInfo:
    """Return IdentifierInfo from links."""
    return IdentifierInfo(
        doi=_extract_identifier(links, "doi"),
        isbn=_extract_identifier(links, "isbn"),
        handle=_extract_identifier(links, "handle"),
    )

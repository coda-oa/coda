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
)


def flatten_detailed(dto: FundingRequestExportDto) -> list[dict[str, str]]:

    rows = []

    for invoice in dto.invoices:
        for position in invoice.positions:
            if not position.funding_assignments:
                # No split: one row with full position amount
                row = _create_row(
                    funding_request=dto.funding_request,
                    invoice=invoice,
                    position=position,
                    assignment=None,
                    funded_amount=position.amount,
                )
                rows.append(row)
            else:
                # Split: one row per assignment
                for assignment in position.funding_assignments:
                    row = _create_row(
                        funding_request=dto.funding_request,
                        invoice=invoice,
                        position=position,
                        assignment=assignment,
                        funded_amount=assignment.amount or Decimal("0"),
                    )
                    rows.append(row)

    return rows


def _create_row(
    funding_request: FundingRequestImportDto,
    invoice: InvoiceImportDto,
    position: PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto,
    assignment: FundingAssignmentImportDto | None,
    funded_amount: Decimal,
) -> dict[str, str]:

    # Start with funding request fields
    row = {
        # Funding Request
        "legacy_request_id": funding_request.legacy_request_id or "",
        "request_date": funding_request.request_date.isoformat(),
        # Publication
        "publication_title": funding_request.publication.title,
        "publication_kind": funding_request.publication.kind,
        "eissn": funding_request.publication.eissn or "",
        "journal_name": funding_request.publication.journal_name,
        "publisher_name": funding_request.publication.publisher_name,
        "license": funding_request.publication.license.value,
        "open_access_type": funding_request.publication.open_access_type.value,
        # Authors (concatenate to string)
        "authors": _format_authors(funding_request.publication.authors),
        # Identifiers (extract from links)
        "doi": _extract_identifier(funding_request.publication.links, "doi"),
        "isbn": _extract_identifier(funding_request.publication.links, "isbn"),
        "handle": _extract_identifier(funding_request.publication.links, "handle"),
        # Publishing state
        "publishing_state": funding_request.publication.publishing_state.state or "",
        "online_date": (
            funding_request.publication.publishing_state.online_date.isoformat()
            if funding_request.publication.publishing_state.online_date
            else ""
        ),
        "print_date": (
            funding_request.publication.publishing_state.print_date.isoformat()
            if funding_request.publication.publishing_state.print_date
            else ""
        ),
        # Vocabulary concepts
        "subject_area": funding_request.publication.subject_area.name or "",
        "publication_type": funding_request.publication.publication_type.name or "",
        # Estimated cost
        "estimated_amount": str(funding_request.estimated_cost.amount),
        "estimated_currency": funding_request.estimated_cost.currency,
        "payment_method": (
            funding_request.estimated_cost.payment_method.value
            if funding_request.estimated_cost.payment_method
            else ""
        ),
        # Review
        "review_result": (
            funding_request.review.result.value if funding_request.review.result else ""
        ),
        "review_remarks": funding_request.review.remarks or "",
        "decided_funding_amount": (
            str(funding_request.review.funding.amount) if funding_request.review.funding else ""
        ),
        "decided_funding_currency": (
            funding_request.review.funding.currency if funding_request.review.funding else ""
        ),
        # Labels
        "labels": "; ".join(funding_request.labels),
        # External funding (take first one if exists)
        "project_id": (
            funding_request.research_funding[0].project_id
            if funding_request.research_funding
            else ""
        ),
        "project_name": (
            funding_request.research_funding[0].project_name
            if funding_request.research_funding
            else ""
        ),
        "funding_organization": (
            funding_request.research_funding[0].funder if funding_request.research_funding else ""
        ),
        # Invoice
        "invoice_number": invoice.number,
        "invoice_date": invoice.date.isoformat(),
        "creditor": invoice.creditor,
        "invoice_status": invoice.status.value,
        "invoice_currency": invoice.currency,
        "invoice_comment": invoice.comment or "",
        "external_invoice_id": invoice.external_id or "",
        # Position
        "position_amount": str(position.amount),
        "tax_rate": str(position.tax_rate),
        "cost_type": position.cost_type.value,
        # Position-specific fields
        **_get_position_specific_fields(position),
        # Funding assignment (the split)
        "funded_amount": str(funded_amount),
        "funding_source_name": assignment.name if assignment else "",
        "funding_source_type": assignment.type if assignment else "",
    }

    return row


def _format_authors(authors: list[AuthorImportDto]) -> str:
    if not authors:
        return ""

    author_strings = []
    for author in authors:
        if author.name:
            author_strings.append(author.name)

    return "; ".join(author_strings)


def _extract_identifier(links: list[LinkImportDto], identifier_type: str) -> str:
    for link in links:
        if link.type.lower() == identifier_type.lower():
            return str(link.value)
    return ""


def _get_position_specific_fields(
    position: PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto,
) -> dict[str, str]:
    if isinstance(position, PublicationPositionImportDto):
        return {
            "position_type": "publication",
            "request_id": position.request_id or "",
            "legacy_position_request_id": position.legacy_request_id or "",
            "contract_name": "",
            "contract_year": "",
            "position_description": "",
        }
    elif isinstance(position, ContractPositionImportDto):
        return {
            "position_type": "contract",
            "request_id": "",
            "legacy_position_request_id": "",
            "contract_name": position.contract_name,
            "contract_year": str(position.contract_year),
            "position_description": "",
        }
    else:  # FreePositionImportDto
        return {
            "position_type": "free",
            "request_id": "",
            "legacy_position_request_id": "",
            "contract_name": "",
            "contract_year": "",
            "position_description": position.description,
        }

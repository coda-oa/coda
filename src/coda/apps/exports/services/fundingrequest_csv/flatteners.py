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

    research_funding = (
        funding_request.research_funding[0] if funding_request.research_funding else None
    )

    return {
        "legacy_request_id": funding_request.legacy_request_id or "",
        "request_date": funding_request.request_date.isoformat(),
        "publication_title": funding_request.publication.title,
        "publication_kind": funding_request.publication.kind,
        "eissn": funding_request.publication.eissn or "",
        "journal_name": funding_request.publication.journal_name,
        "publisher_name": funding_request.publication.publisher_name,
        "license": funding_request.publication.license.value,
        "open_access_type": funding_request.publication.open_access_type.value,
        "authors": _format_authors(funding_request.publication.authors),
        "doi": _extract_identifier(
            funding_request.publication.links,
            "doi",
        ),
        "isbn": _extract_identifier(
            funding_request.publication.links,
            "isbn",
        ),
        "handle": _extract_identifier(
            funding_request.publication.links,
            "handle",
        ),
        "publishing_state": (funding_request.publication.publishing_state.state or ""),
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
        "subject_area": (funding_request.publication.subject_area.name or ""),
        "publication_type": (funding_request.publication.publication_type.name or ""),
        "estimated_amount": str(funding_request.estimated_cost.amount),
        "estimated_currency": (funding_request.estimated_cost.currency),
        "payment_method": (
            funding_request.estimated_cost.payment_method.value
            if funding_request.estimated_cost.payment_method
            else ""
        ),
        "review_result": (
            funding_request.review.result.value if funding_request.review.result else ""
        ),
        "review_remarks": (funding_request.review.remarks or ""),
        "decided_funding_amount": (
            str(funding_request.review.funding.amount) if funding_request.review.funding else ""
        ),
        "decided_funding_currency": (
            funding_request.review.funding.currency if funding_request.review.funding else ""
        ),
        "labels": "; ".join(funding_request.labels),
        "project_id": (research_funding.project_id if research_funding else ""),
        "project_name": (research_funding.project_name if research_funding else ""),
        "funding_organization": (research_funding.funder if research_funding else ""),
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
                "request_id": "",
                "legacy_position_request_id": "",
                "contract_name": "",
                "contract_year": "",
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


def _extract_identifier(links: list[LinkImportDto], identifier_type: str) -> str:
    for link in links:
        if link.type.lower() == identifier_type.lower():
            return str(link.value)
    return ""

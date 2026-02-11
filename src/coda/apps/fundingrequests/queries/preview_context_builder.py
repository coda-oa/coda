"""Context builder for DOI preview detail view.

Converts session-stored DTOs to Detail models that the template expects.
This allows reusing the existing fundingrequest_detail.html template structure.
"""

from typing import Any

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.queries.models import (
    AuthorDetail,
    ExternalFundingDetail,
    PublicationDetail,
    UnpaidDetail,
)
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from coda.contexts.fundingrequest.dto.commands import ExternalFundingDto, PaymentDto
from coda.domain.author import Role
from coda.domain.orcid import Orcid


def build_preview_context(
    session_data: dict[str, Any],
    session_key: str,
) -> dict[str, Any]:
    """Build template context from session DTOs.

    Args:
        session_data: Session data containing DTOs in to_post_data() format
        session_key: Session key for edit URL generation

    Returns:
        Context dict compatible with fundingrequest_detail.html template
    """
    # Reconstruct DTOs from session data
    publication_dto = PublicationDto.model_validate(session_data["publication"])
    payment_dto = PaymentDto.model_validate(session_data["payment"])
    funding_dtos = [ExternalFundingDto.model_validate(f) for f in session_data["funding"]]

    # Build detail models
    publication_detail = _build_publication_detail_from_dto(publication_dto, session_key)
    external_funding_details = _build_external_funding_details(funding_dtos)

    # Build a minimal funding request object for template
    # Note: This is just for display, not a real domain object
    class PreviewFundingRequest:
        """Minimal object to satisfy template expectations."""

        def __init__(self, payment_dto: PaymentDto):
            self.estimated_cost = type(
                "EstimatedCost",
                (),
                {
                    "amount": type(
                        "Amount",
                        (),
                        {
                            "amount": payment_dto.amount,
                            "currency": type("Currency", (), {"code": payment_dto.currency})(),
                        },
                    )(),
                    "method": type("Method", (), {"value": payment_dto.method})(),
                },
            )()
            self.external_costsplitting = payment_dto.external_costsplitting
            self.funding_amount = None  # Not set in preview

    preview_fr = PreviewFundingRequest(payment_dto)

    return {
        "session_key": session_key,
        "publication": publication_detail,
        "funding_request": preview_fr,
        "external_funding": external_funding_details,
        "contact": None,  # TODO: Add contact support
        "is_preview": True,  # Flag to indicate this is preview mode
    }


def _build_publication_detail_from_dto(
    publication_dto: PublicationDto,
    session_key: str,
) -> PublicationDetail:
    """Convert PublicationDto to PublicationDetail.

    Args:
        publication_dto: DTO from session
        session_key: Session key for edit URL generation

    Returns:
        PublicationDetail ready for template rendering
    """
    # Fetch journal to get name and publisher
    journal = Journal.objects.select_related("publisher").get(pk=publication_dto.journal.id)

    # Convert authors
    author_details = _build_author_details_from_dtos(publication_dto.relevant_authors)

    # Convert links
    links = [link_dto.to_link() for link_dto in publication_dto.links]

    # Extract publication date
    meta = publication_dto.meta
    publication_date = (
        meta.online_publication_date if meta.publication_state.lower() == "published" else None
    )

    # Build edit URL - will be updated to point to DOI import wizard
    # For now, use a placeholder
    edit_url = f"#edit-publication-{session_key}"  # TODO: Replace with actual wizard URL

    return PublicationDetail(
        edit_url=edit_url,
        title=meta.title,
        request_remarks="",  # Not in publication DTO
        relevant_authors=author_details,
        other_authors=publication_dto.other_authors,
        publishing_entity_type="Journal",
        publishing_entity_name=f"{journal.title}, {journal.publisher.name}",
        publishing_entity_identifier_name="EISSN",
        publishing_entity_identifier=journal.eissn,
        publication_state=meta.publication_state,
        publication_date=publication_date,
        license=meta.license,
        publication_type=meta.publication_type.name,
        subject_area=meta.subject_area.name,
        oa_type=meta.open_access_type,
        references=links,
        contracts=[],  # TODO: Add contract support
        payment_details=UnpaidDetail(),  # Preview is always unpaid
    )


def _build_author_details_from_dtos(author_dtos: list[Any]) -> list[AuthorDetail]:
    """Convert AuthorDtos to AuthorDetails with affiliation names resolved.

    Args:
        author_dtos: List of AuthorDto objects

    Returns:
        List of AuthorDetail with institution names
    """
    result = []

    # Collect all affiliation IDs
    affiliation_ids = [dto.affiliation for dto in author_dtos if dto.affiliation]

    # Bulk fetch institutions
    institutions = {
        inst.pk: inst.name for inst in Institution.objects.filter(id__in=affiliation_ids)
    }

    for dto in author_dtos:
        affiliation_name = ""
        if dto.affiliation:
            affiliation_name = institutions.get(dto.affiliation, f"Unknown ({dto.affiliation})")

        orcid = Orcid(dto.orcid) if dto.orcid else None
        role = Role[dto.role] if dto.role else Role.CO_AUTHOR

        result.append(
            AuthorDetail(
                name=dto.name,
                email=dto.email or "",
                affiliation=affiliation_name,
                role=role,
                orcid=orcid,
            )
        )

    return result


def _build_external_funding_details(
    funding_dtos: list[ExternalFundingDto],
) -> list[ExternalFundingDetail]:
    """Convert ExternalFundingDtos to ExternalFundingDetails.

    Args:
        funding_dtos: List of ExternalFundingDto objects

    Returns:
        List of ExternalFundingDetail with organization names resolved
    """
    if not funding_dtos:
        return []

    # Bulk fetch organization names
    org_ids = [f.organization for f in funding_dtos]
    orgs = FundingOrganization.objects.filter(id__in=org_ids).values("id", "name")
    org_map = {org["id"]: org["name"] for org in orgs}

    return [
        ExternalFundingDetail(
            organization=org_map.get(f.organization, f"Unknown ({f.organization})"),
            project_id=f.project_id,
            project_name=f.project_name,
        )
        for f in funding_dtos
    ]

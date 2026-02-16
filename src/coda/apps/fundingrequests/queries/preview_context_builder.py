"""Context builder for DOI preview detail view.

Converts session-stored DTOs to domain objects and detail models.
This allows reusing the existing fundingrequest_detail.html template structure.
"""

from typing import Any

from coda.apps.authors.dto import AuthorDto
from coda.apps.institutions import repository as institution_repository
from coda.apps.publications.dto import PublicationDto
from coda.contexts.fundingrequest.dto.commands import (
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.domain.author import Role
from coda.domain.fundingrequest import FundingRequest
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.orcid import Orcid

from .builders import (
    build_external_funding_details,
    build_publication_detail_from_domain,
    get_publication_edit_url,
)
from .models import AuthorDetail, UnpaidDetail


def build_preview_context(session_data: dict[str, Any], session_key: str) -> dict[str, Any]:
    """Build template context from session DTOs.

    Converts DTOs to actual domain objects (FundingRequest, Publication, etc.)
    so the template can use the same structure as the regular detail view.

    Args:
        session_data: Session data containing DTOs in to_post_data() format
        session_key: Session key for edit URL generation

    Returns:
        Context dict compatible with fundingrequest_detail.html template
    """
    publication_dto = PublicationDto.model_validate(session_data["publication"])
    payment_dto = PaymentDto.model_validate(session_data["payment"])
    funding_dtos = [ExternalFundingDto.model_validate(f) for f in session_data["funding"]]
    extra_info_dto = ExtraInformationDto.model_validate(session_data["extra_information"])

    publication = publication_dto.to_publication()
    payment = payment_dto.to_payment()
    external_funding = [f.to_external_funding() for f in funding_dtos]
    extra_contact = extra_info_dto.extra_contact.to_contact()
    preview_request_id = PublicFundingRequestId.temporary()

    preview_fr = FundingRequest(
        id=None,
        request_id=preview_request_id,
        publication=publication,
        estimated_cost=payment,
        external_funding=external_funding,
        extra_contact=extra_contact,
        request_remarks=extra_info_dto.request_remarks,
    )

    author_details = _build_author_details_from_dtos(publication_dto.relevant_authors)
    edit_url = get_publication_edit_url(publication, fr_id=None)
    payment_details = UnpaidDetail()

    publication_detail = build_publication_detail_from_domain(
        pub=publication,
        author_details=author_details,
        edit_url=edit_url,
        request_remarks=extra_info_dto.request_remarks,
        payment_details=payment_details,
    )
    external_funding_details = build_external_funding_details(external_funding)

    return {
        "session_key": session_key,
        "publication": publication_detail,
        "funding_request": preview_fr,
        "external_funding": external_funding_details,
        "contact": extra_contact,
        "is_preview": True,
    }


def _build_author_details_from_dtos(author_dtos: list[AuthorDto]) -> list[AuthorDetail]:
    """Convert AuthorDtos to AuthorDetails with affiliation names resolved.

    Args:
        author_dtos: List of AuthorDto objects

    Returns:
        List of AuthorDetail with institution names
    """
    result = []

    affiliation_ids = [dto.affiliation for dto in author_dtos if dto.affiliation]
    institutions = {
        inst.pk: inst.name for inst in institution_repository.get_many_by_id(affiliation_ids)
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

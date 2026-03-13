"""Context builder for DOI preview detail view.

Converts session-stored preview DTOs to detail models.
This allows reusing the existing fundingrequest_detail.html template structure.
"""

from typing import Any, Literal

from coda.apps.authors.dto import AuthorDto
from coda.apps.institutions import repository as institution_repository
from coda.contexts.publication.dto.preview import (
    PreviewArticle,
    PreviewFundingRequest,
    PreviewMonograph,
)
from coda.domain.author import Role
from coda.domain.orcid import Orcid
from coda.domain.publication.links import Doi, Isbn, Link

from .models import AuthorDetail, PublicationDetail, UnpaidDetail


def build_preview_context(preview_fr: PreviewFundingRequest, session_key: str) -> dict[str, Any]:
    """Build template context from a PreviewFundingRequest DTO.

    Builds a preview-specific context WITHOUT creating database entities.
    Read-only lookups (e.g. institution names for authors) are performed but
    nothing is persisted. This is different from the regular detail view
    which uses actual persisted data.

    Args:
        preview_fr: PreviewFundingRequest DTO (already built by the view)
        session_key: Session key for identifying this preview

    Returns:
        Context dict compatible with fundingrequest_detail.html template
    """
    # Build author details from preview authors
    author_details = _build_author_details_from_dtos(preview_fr.publication.authors)

    # Build publication detail directly from preview DTO (no domain objects needed)
    publication_detail = _build_publication_detail_from_preview(
        preview_pub=preview_fr.publication,
        author_details=author_details,
    )

    current_type = (
        "article" if preview_fr.publication.publication_kind == "journal_article" else "monograph"
    )

    return {
        "session_key": session_key,
        "publication": publication_detail,
        "is_preview": True,
        "current_publication_type": current_type,
        "warnings": preview_fr.warnings,
    }


def _build_publication_detail_from_preview(
    preview_pub: PreviewArticle | PreviewMonograph,
    author_details: list[AuthorDetail],
) -> PublicationDetail:
    """Build PublicationDetail directly from preview DTO without database lookups.

    This is preview-specific and doesn't require journal/publisher to exist in database.

    Args:
        preview_pub: Preview publication DTO
        author_details: Already-converted author details

    Returns:
        PublicationDetail ready for template display
    """
    # Determine publishing entity info from preview data
    entity_type: Literal["Journal", "Publisher"]
    if isinstance(preview_pub, PreviewArticle):
        entity_type = "Journal"
        if preview_pub.journal is not None:
            entity_name = preview_pub.journal.title
            if preview_pub.publisher_name:
                entity_name = f"{entity_name}, {preview_pub.publisher_name}"
            identifier_name = "EISSN" if preview_pub.journal.eissn else ""
            identifier = preview_pub.journal.eissn or ""
        else:
            entity_name = "(journal not specified)"
            identifier_name = ""
            identifier = ""
    else:  # PreviewMonograph
        entity_type = "Publisher"
        entity_name = preview_pub.publisher_name or "(publisher not specified)"
        identifier_name = ""
        identifier = ""

    # Extract publication date from state
    publication_date = (
        preview_pub.meta.online_publication_date or preview_pub.meta.print_publication_date
    )

    # Build links from DOI (and ISBN for monographs)
    links: list[Link] = [Doi(preview_pub.doi)]
    if isinstance(preview_pub, PreviewMonograph) and preview_pub.isbn:
        links.append(Isbn(preview_pub.isbn))

    return PublicationDetail(
        edit_url="",  # Preview is read-only
        title=preview_pub.meta.title,
        request_remarks="",  # No remarks in preview
        relevant_authors=author_details,
        other_authors=[],  # Preview doesn't have other authors
        publishing_entity_type=entity_type,
        publishing_entity_name=entity_name,
        publishing_entity_identifier_name=identifier_name,
        publishing_entity_identifier=identifier,
        publication_state=preview_pub.meta.publication_state,
        publication_date=publication_date,
        license=preview_pub.meta.license,
        publication_type=preview_pub.meta.publication_type.name,
        subject_area=preview_pub.meta.subject_area.name,
        oa_type=preview_pub.meta.open_access_type,
        references=links,
        contracts=[],  # No contracts in preview
        payment_details=UnpaidDetail(),  # Preview is always unpaid
    )


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

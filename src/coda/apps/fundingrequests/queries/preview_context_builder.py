"""Context builder for DOI preview detail view.

Converts session-stored preview DTOs to domain objects and detail models.
This allows reusing the existing fundingrequest_detail.html template structure.
"""

from decimal import Decimal
from typing import Any, Literal

from coda.apps.authors.dto import AuthorDto
from coda.apps.institutions import repository as institution_repository
from coda.contexts.publication.dto.preview import (
    PreviewArticle,
    PreviewFundingRequest,
    PreviewMonograph,
)
from coda.domain.author import Author, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, NoContact, Payment, PaymentMethod
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.money import Currency, Money
from coda.domain.orcid import Orcid
from coda.domain.publication import (
    JournalId,
    License,
    Monograph,
    Publication,
    Published,
    Unpublished,
)
from coda.domain.publication.links import Doi, Isbn, Link
from coda.domain.string import NonEmptyStr

from .models import AuthorDetail, PublicationDetail, UnpaidDetail


def build_preview_context(session_data: dict[str, Any], session_key: str) -> dict[str, Any]:
    """Build template context from session preview DTOs.

    Builds a preview-specific context WITHOUT creating database entities or
    requiring database lookups. This is different from the regular detail view
    which uses actual persisted data.

    Args:
        session_data: Session data containing PreviewFundingRequest in model_dump() format
        session_key: Session key for identifying this preview

    Returns:
        Context dict compatible with fundingrequest_detail.html template
    """
    preview_fr = PreviewFundingRequest.model_validate(session_data)

    # Create default payment for preview (always 0.0 EUR, method unknown)
    # Payment details are not shown in preview and will be set during import
    payment = Payment(
        amount=Money(Decimal("0.0"), Currency.EUR),
        method=PaymentMethod.Unknown,
    )

    # Build author details from preview authors
    author_details = _build_author_details_from_dtos(preview_fr.publication.authors)

    # Build publication detail directly from preview DTO (no domain objects needed)
    publication_detail = _build_publication_detail_from_preview(
        preview_pub=preview_fr.publication,
        author_details=author_details,
    )

    # Create minimal domain publication for the FundingRequest
    # (FundingRequest needs a publication, but we use preview data)
    publication = _convert_preview_publication_to_domain(preview_fr.publication)

    # Create temporary funding request for preview
    preview_request_id = PublicFundingRequestId.temporary()
    funding_request = FundingRequest(
        id=None,
        request_id=preview_request_id,
        publication=publication,
        estimated_cost=payment,
        external_funding=[],  # No external funding in preview
        extra_contact=NoContact,  # Use singleton, not callable
        request_remarks="",  # Empty string, not None
    )

    return {
        "session_key": session_key,
        "publication": publication_detail,
        "funding_request": funding_request,
        "external_funding": [],
        "contact": NoContact,  # Use singleton, not callable
        "is_preview": True,
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
        # For preview, show journal title and publisher name if available
        entity_name = preview_pub.journal.title
        if preview_pub.publisher_name:
            entity_name = f"{entity_name}, {preview_pub.publisher_name}"
        identifier_name = "EISSN" if preview_pub.journal.eissn else "ISSN"
        identifier = preview_pub.journal.eissn or preview_pub.journal.issn or ""
    else:  # PreviewMonograph
        entity_type = "Publisher"
        entity_name = preview_pub.publisher_name
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


def _convert_preview_publication_to_domain(
    preview_pub: PreviewArticle | PreviewMonograph,
) -> Publication | Monograph:
    """Convert preview publication DTO to minimal domain Publication for display.

    Note: This creates a Publication WITHOUT real database IDs (journal/publisher).
    Uses placeholder ID (-1) for preview display only, not for persistence.
    """
    # Convert authors to domain Authors
    authors_list = [
        Author.new(
            name=NonEmptyStr(a.name),
            role=Role[a.role] if a.role else Role.CO_AUTHOR,
            email=a.email or "",  # Convert None to empty string
            orcid=Orcid(a.orcid) if a.orcid else None,  # Convert str to Orcid
            affiliation=a.affiliation,
        )
        for a in preview_pub.authors
    ]

    # Convert publication state from dates
    pub_state: Published | Unpublished
    if preview_pub.meta.online_publication_date or preview_pub.meta.print_publication_date:
        pub_state = Published(
            online=preview_pub.meta.online_publication_date,
            print=preview_pub.meta.print_publication_date,
        )
    else:
        # Parse unpublished state from string
        pub_state = Unpublished.of(preview_pub.meta.publication_state)

    # Convert license string to License enum
    license_obj = License.of(preview_pub.meta.license)

    # Build links set from DOI (and ISBN for monographs)
    # Type as set[Link] since Doi and Isbn implement the Link protocol
    links: set[Link] = {Doi(preview_pub.doi)}
    if isinstance(preview_pub, PreviewMonograph) and preview_pub.isbn:
        links.add(Isbn(preview_pub.isbn))

    # Build appropriate publication type (Article vs Monograph)
    if isinstance(preview_pub, PreviewArticle):
        # Use placeholder JournalId for preview (-1)
        return Publication.new(
            title=NonEmptyStr(preview_pub.meta.title),
            journal=JournalId(-1),  # Placeholder for preview
            relevant_authors=authors_list,
            license=license_obj,
            publication_state=pub_state,
            links=links,
        )
    else:
        # Use placeholder PublisherId for preview (-1)
        return Monograph.new(
            title=NonEmptyStr(preview_pub.meta.title),
            publisher=PublisherId(-1),  # Placeholder for preview
            relevant_authors=authors_list,
            license=license_obj,
            publication_state=pub_state,
            links=links,
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

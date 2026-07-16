"""Metadata mapping - Transform external DOI metadata to internal DTOs.

This module contains pure transformation functions that convert external publication
metadata (from Crossref, DataCite, etc.) into CODA's internal DTO structures.

Two types of DTOs are built:
1. Preview DTOs - No database IDs, used for preview workflows
2. Persistence DTOs - Include resolved database IDs, used for actual import

All functions are pure (no side effects, no database queries).
"""

import datetime

from coda.apps.authors.dto import AuthorDto
from coda.apps.publications.dto import ConceptDto
from coda.contexts.fundingrequest.dto.external_metadata import (
    ExternalAuthor,
    ExternalPublicationMetadata,
)
from coda.contexts.fundingrequest.dto.preview import (
    PreviewArticle,
    PreviewExternalFunding,
    PreviewJournal,
    PreviewMonograph,
    PreviewPublicationMeta,
)
from coda.domain.author import Role
from coda.domain.orcid import Orcid
from coda.domain.publication import License
from coda.domain.publication.links import Doi
from coda.domain.publication.publication import (
    InvalidLicenseType,
    PublicationState,
    Published,
    Unpublished,
)
from coda.domain.vocabulary import UnknownConcept


def _map_license(license_str: str | None) -> License:
    """Map license string to CODA License enum.

    Args:
        license_str: License identifier (e.g., "CC-BY-4.0")

    Returns:
        License enum value, or License.Unknown if invalid/missing

    Example:
        >>> map_license("CC-BY-4.0")
        License.CC_BY_4_0
        >>> map_license(None)
        License.Unknown
        >>> map_license("invalid")
        License.Unknown
    """
    if not license_str:
        return License.Unknown

    try:
        return License.of(license_str)
    except InvalidLicenseType:
        return License.Unknown


def _map_publication_state(
    online_date: datetime.date | None,
    print_date: datetime.date | None,
) -> PublicationState:
    """Map publication dates to publication state.

    Args:
        online_date: Online publication date
        print_date: Print publication date

    Returns:
        Published state if any date exists, otherwise Unpublished

    Example:
        >>> map_publication_state(date(2023, 1, 15), None)
        Published(online=date(2023, 1, 15), print=None)
        >>> map_publication_state(None, None)
        Unpublished()
    """
    if online_date or print_date:
        return Published(online=online_date, print=print_date)
    return Unpublished()


def _extract_online_date(publication_state: PublicationState) -> datetime.date | None:
    """Extract online publication date if state is Published.

    Args:
        publication_state: Publication state object

    Returns:
        Online date if Published, None otherwise
    """
    return publication_state.online if isinstance(publication_state, Published) else None


def _extract_print_date(publication_state: PublicationState) -> datetime.date | None:
    """Extract print publication date if state is Published.

    Args:
        publication_state: Publication state object

    Returns:
        Print date if Published, None otherwise
    """
    return publication_state.print if isinstance(publication_state, Published) else None


def _build_meta(metadata: ExternalPublicationMetadata) -> PreviewPublicationMeta:
    """Build shared publication metadata from external metadata.

    Extracts and maps all common publication fields (title, license, dates, etc.)
    into a PreviewPublicationMeta.  Used by both article and monograph builders.

    Args:
        metadata: External publication metadata

    Returns:
        PreviewPublicationMeta with all common fields populated
    """
    publication_state = _map_publication_state(
        metadata.online_publication_date,
        metadata.print_publication_date,
    )
    return PreviewPublicationMeta(
        title=metadata.title,
        publication_type=ConceptDto.from_concept(UnknownConcept),
        subject_area=ConceptDto.from_concept(UnknownConcept),
        license=_map_license(metadata.license).name,
        open_access_type="Unknown",
        publication_state=publication_state.name(),
        online_publication_date=_extract_online_date(publication_state),
        print_publication_date=_extract_print_date(publication_state),
    )


def build_preview_article(
    doi: Doi,
    metadata: ExternalPublicationMetadata,
) -> PreviewArticle:
    """Build PreviewArticle from DOI metadata - no database entities created.

    Args:
        doi: DOI identifier
        metadata: External publication metadata
        authors_dto: List of author DTOs

    Returns:
        PreviewArticle DTO ready for preview workflows.  When journal metadata
        is absent the returned DTO will have ``journal=None`` and a non-empty
        ``warnings`` list so the caller can present a fix form to the user.
    """
    journal = (
        PreviewJournal(
            title=metadata.journal.title,
            issn=metadata.journal.issn,
            eissn=metadata.journal.eissn,
        )
        if metadata.journal is not None
        else None
    )

    return PreviewArticle(
        meta=_build_meta(metadata),
        journal=journal,
        doi=str(doi),
        authors=_build_authors_dto(metadata.authors),
        publisher_name=metadata.publisher,
        funding=[
            PreviewExternalFunding(
                name=f.funder.name,
                identifiers=f.funder.identifiers,
                project_id=f.project_id,
            )
            for f in metadata.funders
        ],
    )


def build_preview_monograph(
    doi: Doi,
    metadata: ExternalPublicationMetadata,
) -> PreviewMonograph:
    """Build PreviewMonograph from DOI metadata - no database entities created.

    Args:
        doi: DOI identifier
        metadata: External publication metadata
        authors_dto: List of author DTOs

    Returns:
        PreviewMonograph DTO ready for preview workflows.  When publisher
        metadata is absent the returned DTO will have ``publisher_name=None``
        and a non-empty ``warnings`` list so the caller can present a fix form.
    """
    return PreviewMonograph(
        meta=_build_meta(metadata),
        publisher_name=metadata.publisher,
        doi=str(doi),
        isbn=metadata.isbn,
        authors=_build_authors_dto(metadata.authors),
        funding=[
            PreviewExternalFunding(
                name=f.funder.name, identifiers=f.funder.identifiers, project_id=f.project_id
            )
            for f in metadata.funders
        ],
    )


def _build_authors_dto(external_authors: list[ExternalAuthor]) -> list[AuthorDto]:
    """Convert external author metadata to AuthorDto objects."""
    authors = []

    for external_author in external_authors:
        normalized_name = _normalize_author_name(
            external_author.name,
            external_author.affiliation,
            external_author.orcid,
        )
        if normalized_name is None:
            continue

        orcid = None
        if external_author.orcid:
            orcid = Orcid(external_author.orcid)

        authors.append(
            AuthorDto(
                name=normalized_name,
                email="",
                orcid=orcid,
                affiliation=None,
                role=Role.CO_AUTHOR.name,
            )
        )

    return authors


def _normalize_author_name(name: str, affiliation: str | None, ror_id: str | None) -> str | None:
    """Normalize author name, returning None if author should be skipped.

    Returns the trimmed name if valid, "Unknown" if name is empty but other data exists,
    or None if author has no usable data.
    """
    small_space = "\u2009"
    trimmed_name = name.strip().replace(small_space, " ")

    has_other_data = affiliation is not None or ror_id is not None

    if trimmed_name:
        return trimmed_name
    elif has_other_data:
        return "Unknown"
    else:
        return None

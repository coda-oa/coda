"""DOI Import Service - Creates FundingRequests from DOI metadata."""

import datetime
from collections.abc import Callable, Iterable
from typing import Literal

from coda.apps.authors.dto import AuthorDto
from coda.apps.journals import services as journal_services
from coda.apps.publications.dto import (
    ConceptDto,
    JournalDto,
    LinkDto,
    MonographDto,
    PublicationDto,
    PublicationMetaDto,
)
from coda.apps.publications.repositories import publication_repository
from coda.apps.publishers import services as publisher_services
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.dto.preview import (
    PreviewArticle,
    PreviewFundingRequest,
    PreviewJournal,
    PreviewMonograph,
    PreviewPublicationMeta,
)
from coda.contexts.publication.services.crossref_type_detector import detect_publication_type
from coda.contexts.publication.services.doi_client import DOIMetadataClient
from coda.domain.author import Author, Role
from coda.domain.contract import PublisherId
from coda.domain.errors import DomainError
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.issn import Issn
from coda.domain.publication import JournalId, License, PublicationId
from coda.domain.publication.links import Doi
from coda.domain.publication.publication import (
    InvalidLicenseType,
    PublicationState,
    Published,
    Unpublished,
)
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import UnknownConcept


def _map_license(license_str: str | None) -> License:
    """Map license string to CODA License enum."""
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
    """Map publication dates to publication state."""
    if online_date or print_date:
        return Published(online=online_date, print=print_date)
    return Unpublished()


def _extract_online_date(publication_state: PublicationState) -> datetime.date | None:
    """Extract online publication date if state is Published."""
    return publication_state.online if isinstance(publication_state, Published) else None


def _extract_print_date(publication_state: PublicationState) -> datetime.date | None:
    """Extract print publication date if state is Published."""
    return publication_state.print if isinstance(publication_state, Published) else None


def _build_preview_article(
    doi: Doi,
    metadata: ExternalPublicationMetadata,
    authors_dto: list[AuthorDto],
) -> PreviewArticle:
    """Build PreviewArticle from DOI metadata - no database entities created."""
    publication_state = _map_publication_state(
        metadata.online_publication_date,
        metadata.print_publication_date,
    )

    if metadata.journal is None:
        raise InvalidMetadataError("Journal article missing journal metadata")

    return PreviewArticle(
        meta=PreviewPublicationMeta(
            title=metadata.title,
            publication_type=ConceptDto.from_concept(UnknownConcept),
            subject_area=ConceptDto.from_concept(UnknownConcept),
            license=_map_license(metadata.license).name,
            open_access_type="Unknown",
            publication_state=publication_state.name(),
            online_publication_date=_extract_online_date(publication_state),
            print_publication_date=_extract_print_date(publication_state),
        ),
        journal=PreviewJournal(
            title=metadata.journal.title,
            issn=metadata.journal.issn,
            eissn=metadata.journal.eissn,
        ),
        doi=str(doi),
        authors=authors_dto,
        publisher_name=metadata.publisher,
    )


def _build_preview_monograph(
    doi: Doi,
    metadata: ExternalPublicationMetadata,
    authors_dto: list[AuthorDto],
) -> PreviewMonograph:
    """Build PreviewMonograph from DOI metadata - no database entities created."""
    publication_state = _map_publication_state(
        metadata.online_publication_date,
        metadata.print_publication_date,
    )

    if metadata.publisher is None:
        raise InvalidMetadataError("Monograph missing publisher name")

    return PreviewMonograph(
        meta=PreviewPublicationMeta(
            title=metadata.title,
            publication_type=ConceptDto.from_concept(UnknownConcept),
            subject_area=ConceptDto.from_concept(UnknownConcept),
            license=_map_license(metadata.license).name,
            open_access_type="Unknown",
            publication_state=publication_state.name(),
            online_publication_date=_extract_online_date(publication_state),
            print_publication_date=_extract_print_date(publication_state),
        ),
        publisher_name=metadata.publisher,
        doi=str(doi),
        isbn=metadata.isbn,
        authors=authors_dto,
    )


PreviewBuilder = Callable[
    [Doi, ExternalPublicationMetadata, list[AuthorDto]],
    PreviewArticle | PreviewMonograph,
]

_PREVIEW_BUILDERS: dict[Literal["article", "monograph"], PreviewBuilder] = {
    "article": _build_preview_article,
    "monograph": _build_preview_monograph,
}


class DOIAlreadyImported(DomainError):
    """Raised when attempting to import a DOI that already exists in the database."""

    def __init__(
        self,
        doi: Doi,
        existing_publication_id: PublicationId,
        existing_publication_title: str,
        existing_publication_authors: Iterable[Author],
    ) -> None:
        self.doi = doi
        self.publication_id = existing_publication_id
        self.publication_title = existing_publication_title
        self.publication_authors = existing_publication_authors
        super().__init__(
            "\n".join(
                (
                    f"DOI {doi} already exists in database.",
                    f"Title: {existing_publication_title}",
                    f"Authors: {', '.join(a.name for a in existing_publication_authors)}",
                )
            )
        )


class InvalidMetadataError(DomainError):
    """Raised when DOI metadata is invalid or missing required fields."""


class DOIImportService:
    """Import publication metadata from DOI and create a FundingRequest.

    The service uses an optional cache to avoid re-fetching metadata from external APIs.
    """

    def __init__(
        self,
        doi_client: DOIMetadataClient,
        cache: dict[Doi, PreviewFundingRequest] | None = None,
    ) -> None:
        """Initialize the service with a DOI client and optional cache.

        Args:
            doi_client: Client to fetch metadata from external APIs (e.g., Crossref)
            cache: Optional cache of pre-fetched preview DTOs (avoids re-fetching)
        """
        self.doi_client = doi_client
        self.cache = cache or {}

    def fetch_doi_preview(self, doi: Doi) -> PreviewFundingRequest:
        """Build a preview FundingRequest DTO without creating database entities.

        This method does NOT check if the DOI already exists and does NOT create
        journals, publishers, or funding requests. Use this for preview workflows
        where you want to show the user what will be imported before persisting.

        Args:
            doi: The DOI to import

        Returns:
            PreviewFundingRequest with publication metadata (no database IDs)

        Raises:
            DOINotFoundError: If DOI not found (when fetching)
            DOIFetchError: If fetch fails (when fetching)
            InvalidMetadataError: If metadata is invalid
        """
        if doi in self.cache:
            return self.cache[doi]

        metadata = self.doi_client.fetch(doi)
        detected_type = detect_publication_type(metadata)
        authors_dto = self._build_authors_dto(metadata.authors)

        builder = _PREVIEW_BUILDERS[detected_type]
        publication_preview = builder(doi, metadata, authors_dto)

        return PreviewFundingRequest(publication=publication_preview)

    def import_from_doi(self, doi: Doi) -> FundingRequestId:
        """Fetch metadata from DOI and create a FundingRequest in the database.

        Returns:
            The ID of the created funding request

        Raises:
            DOIAlreadyImported: If DOI already exists
            DOINotFoundError: If DOI not found
            DOIFetchError: If fetch fails
            InvalidMetadataError: If metadata is invalid
        """
        self._ensure_doi_not_already_imported(doi)
        preview_dto = self.fetch_doi_preview(doi)
        creation_dto = self._convert_preview_to_creation_dto(preview_dto)
        return fundingrequests.create_fundingrequest(creation_dto)

    def _ensure_doi_not_already_imported(self, doi: Doi) -> None:
        """Verify DOI has not been imported previously."""

        existing_publication = publication_repository.find_by_doi(doi)
        if existing_publication:
            if existing_publication.id is None:
                raise InvalidMetadataError("Publication from database missing ID")
            raise DOIAlreadyImported(
                doi,
                existing_publication.id,
                existing_publication.title,
                existing_publication.relevant_authors,
            )

    def _build_publication_dto(
        self,
        doi: Doi,
        metadata: ExternalPublicationMetadata,
        journal_id: JournalId,
        authors_dto: list[AuthorDto],
    ) -> PublicationDto:
        """Build PublicationDto from DOI metadata."""
        publication_state = _map_publication_state(
            metadata.online_publication_date,
            metadata.print_publication_date,
        )

        return PublicationDto(
            meta=PublicationMetaDto(
                title=metadata.title,
                publication_type=ConceptDto.from_concept(UnknownConcept),
                subject_area=ConceptDto.from_concept(UnknownConcept),
                license=_map_license(metadata.license).name,
                open_access_type="Unknown",
                publication_state=publication_state.name(),
                online_publication_date=_extract_online_date(publication_state),
                print_publication_date=_extract_print_date(publication_state),
            ),
            journal=JournalDto(id=journal_id),
            contracts=[],
            links=[LinkDto(link_type=doi.type(), link_value=doi.value())],
            relevant_authors=authors_dto,
            other_authors=[],
        )

    def _build_monograph_dto(
        self,
        doi: Doi,
        metadata: ExternalPublicationMetadata,
        publisher_id: PublisherId,
        authors_dto: list[AuthorDto],
    ) -> MonographDto:
        """Build MonographDto from DOI metadata."""
        publication_state = _map_publication_state(
            metadata.online_publication_date,
            metadata.print_publication_date,
        )

        return MonographDto(
            meta=PublicationMetaDto(
                title=metadata.title,
                publication_type=ConceptDto.from_concept(UnknownConcept),
                subject_area=ConceptDto.from_concept(UnknownConcept),
                license=_map_license(metadata.license).name,
                open_access_type="Unknown",
                publication_state=publication_state.name(),
                online_publication_date=_extract_online_date(publication_state),
                print_publication_date=_extract_print_date(publication_state),
            ),
            publisher=publisher_id,
            contracts=[],
            links=[LinkDto(link_type=doi.type(), link_value=doi.value())],
            relevant_authors=authors_dto,
            other_authors=[],
        )

    def _match_or_create_journal(self, issn: Issn, publication: PreviewArticle) -> JournalId:
        journal = journal_services.find_by_eissn(issn)
        if journal:
            return JournalId(journal.pk)

        if not publication.journal.title:
            raise InvalidMetadataError("Journal missing publisher name")

        if publication.publisher_name is None:
            raise InvalidMetadataError("Journal missing publisher name")

        publisher_id = self._match_or_create_publisher(publication.publisher_name)
        return journal_services.create(
            title=NonEmptyStr(publication.journal.title), eissn=issn, publisher_id=publisher_id
        )

    def _convert_preview_to_creation_dto(
        self, preview: PreviewFundingRequest
    ) -> CreateFundingRequestDto:
        """Convert preview DTO to creation DTO by resolving/creating database entities.

        This is where journals and publishers are matched or created in the database.

        Args:
            preview: PreviewFundingRequest with publication metadata

        Returns:
            CreateFundingRequestDto with resolved database IDs

        Raises:
            InvalidMetadataError: If required metadata is missing
        """
        publication_dto: PublicationDto | MonographDto

        if isinstance(preview.publication, PreviewArticle):
            if preview.publication.journal.eissn is None:
                raise InvalidMetadataError(
                    f"Journal '{preview.publication.journal.title}' missing E-ISSN"
                )

            issn = Issn(preview.publication.journal.eissn)
            journal_id = self._match_or_create_journal(issn, preview.publication)
            publication_dto = preview.publication.to_publication_dto(journal_id=journal_id)

        elif isinstance(preview.publication, PreviewMonograph):
            publisher_id = self._match_or_create_publisher(preview.publication.publisher_name)
            publication_dto = preview.publication.to_monograph_dto(publisher_id=publisher_id)
        else:
            raise ValueError("Invalid Preview type")

        return CreateFundingRequestDto(
            publication=publication_dto,
            payment=PaymentDto.empty(),
            extra_information=ExtraInformationDto(),
            funding=[],
        )

    def _build_authors_dto(self, external_authors: list[ExternalAuthor]) -> list[AuthorDto]:
        """Convert external author metadata to AuthorDto objects."""
        authors = []

        for external_author in external_authors:
            normalized_name = self._normalize_author_name(
                external_author.name,
                external_author.affiliation,
                external_author.ror_id,
            )
            if normalized_name is None:
                continue

            authors.append(
                AuthorDto(
                    name=normalized_name,
                    email="",
                    orcid=None,
                    affiliation=None,
                    role=Role.CO_AUTHOR.name,
                )
            )

        return authors

    def _normalize_author_name(
        self, name: str, affiliation: str | None, ror_id: str | None
    ) -> str | None:
        """Normalize author name, returning None if author should be skipped.

        Returns the trimmed name if valid, "Unknown" if name is empty but other data exists,
        or None if author has no usable data.
        """
        trimmed_name = name.strip()
        has_other_data = affiliation is not None or ror_id is not None

        if trimmed_name:
            return trimmed_name
        elif has_other_data:
            return "Unknown"
        else:
            return None

    def _match_or_create_publisher(self, publisher_name: str) -> PublisherId:
        """Match publisher by name or create a new one."""
        publisher = publisher_services.find_by_name(publisher_name)
        if publisher:
            return PublisherId(publisher.pk)

        return publisher_services.create(name=publisher_name)

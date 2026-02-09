"""DOI Import Service - Creates FundingRequests from DOI metadata."""

import datetime
from typing import TYPE_CHECKING

from coda.apps.authors.dto import AuthorDto
from coda.apps.journals import services as journal_services
from coda.apps.publications.dto import (
    ConceptDto,
    JournalDto,
    LinkDto,
    PublicationDto,
    PublicationMetaDto,
)
from coda.apps.publishers import services as publisher_services
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client import DOIMetadataClient
from coda.domain.author import Role
from coda.domain.contract import PublisherId
from coda.domain.errors import DomainError
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.issn import Issn
from coda.domain.money import Currency
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

if TYPE_CHECKING:
    from coda.apps.publishers.models import Publisher


class DOIAlreadyImported(DomainError):
    """Raised when attempting to import a DOI that already exists in the database."""

    def __init__(self, doi: Doi, existing_publication_id: PublicationId) -> None:
        self.doi = doi
        self.existing_publication_id = existing_publication_id
        super().__init__(
            f"DOI {doi} already exists in database (PublicationId: {existing_publication_id})"
        )


class InvalidMetadataError(DomainError):
    """Raised when DOI metadata is invalid or missing required fields."""


class DOIImportService:
    """Import publication metadata from DOI and create a FundingRequest."""

    def __init__(self, doi_client: DOIMetadataClient) -> None:
        self.doi_client = doi_client

    def prepare_funding_request_dto(self, doi: Doi) -> CreateFundingRequestDto:
        """Fetch metadata from DOI and build a FundingRequest DTO (without persisting).

        This method does NOT check if the DOI already exists. Use this for preview workflows
        where you want to build the DTO before deciding whether to persist.

        Returns:
            CreateFundingRequestDto ready to be used for preview or persistence

        Raises:
            DOINotFoundError: If DOI not found
            DOIFetchError: If fetch fails
            InvalidMetadataError: If metadata is invalid
        """
        metadata = self.doi_client.fetch(doi)

        authors_dto = self._build_authors_dto(metadata.authors)
        journal_id = self._match_or_create_journal(metadata.journal, metadata.publisher)
        publication_dto = self._build_publication_dto(
            doi=doi,
            metadata=metadata,
            journal_id=journal_id,
            authors_dto=authors_dto,
        )

        return CreateFundingRequestDto(
            publication=publication_dto,
            payment=PaymentDto(
                amount=0.0,
                currency=Currency.EUR.code,
                method="unknown",
            ),
            extra_information=ExtraInformationDto(),
            funding=[],
        )

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
        creation_dto = self.prepare_funding_request_dto(doi)
        return fundingrequests.create_fundingrequest(creation_dto)

    def _ensure_doi_not_already_imported(self, doi: Doi) -> None:
        """Verify DOI has not been imported previously."""
        from coda.apps.publications.repositories import publication_repository

        existing_publication = publication_repository.find_by_doi(doi)
        if existing_publication:
            if existing_publication.id is None:
                raise InvalidMetadataError("Publication from database missing ID")
            raise DOIAlreadyImported(doi, existing_publication.id)

    def _build_publication_dto(
        self,
        doi: Doi,
        metadata: ExternalPublicationMetadata,
        journal_id: JournalId,
        authors_dto: list[AuthorDto],
    ) -> PublicationDto:
        """Build PublicationDto from DOI metadata."""
        publication_state = self._map_publication_state(
            metadata.online_publication_date,
            metadata.print_publication_date,
        )

        return PublicationDto(
            meta=PublicationMetaDto(
                title=metadata.title,
                publication_type=ConceptDto.from_concept(UnknownConcept),
                subject_area=ConceptDto.from_concept(UnknownConcept),
                license=self._map_license(metadata.license).name,
                open_access_type="Unknown",
                publication_state=publication_state.name(),
                online_publication_date=self._extract_online_date(publication_state),
                print_publication_date=self._extract_print_date(publication_state),
            ),
            journal=JournalDto(id=journal_id),
            contracts=[],
            links=[LinkDto(link_type=doi.type(), link_value=doi.value())],
            relevant_authors=authors_dto,
            other_authors=[],
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

    def _match_or_create_journal(
        self, external_journal: ExternalJournal | None, publisher_name: str | None
    ) -> JournalId:
        """Match journal by E-ISSN or create if not found."""
        if external_journal is None:
            raise InvalidMetadataError("Journal article missing journal metadata")
        if external_journal.eissn is None:
            raise InvalidMetadataError(f"Journal '{external_journal.title}' missing E-ISSN")
        if publisher_name is None:
            raise InvalidMetadataError("Journal missing publisher name")

        issn = Issn(external_journal.eissn)

        journal = journal_services.find_by_eissn(issn)
        if journal:
            return JournalId(journal.pk)

        publisher = self._match_or_create_publisher(publisher_name)
        journal_id = journal_services.create(
            title=NonEmptyStr(external_journal.title),
            eissn=issn,
            publisher_id=PublisherId(publisher.pk),
        )
        return journal_id

    def _match_or_create_publisher(self, publisher_name: str) -> "Publisher":
        """Match publisher by name or create a new one."""
        publisher = publisher_services.find_by_name(publisher_name)
        if publisher:
            return publisher

        publisher_id = publisher_services.create(name=publisher_name)
        from coda.apps.publishers.models import Publisher

        return Publisher.objects.get(pk=publisher_id)

    def _map_license(self, license_str: str | None) -> License:
        """Map license string to CODA License enum."""
        if not license_str:
            return License.Unknown

        try:
            return License.of(license_str)
        except InvalidLicenseType:
            return License.Unknown

    def _map_publication_state(
        self,
        online_date: datetime.date | None,
        print_date: datetime.date | None,
    ) -> PublicationState:
        """Map publication dates to publication state."""
        if online_date or print_date:
            return Published(online=online_date, print=print_date)
        return Unpublished()

    def _extract_online_date(self, publication_state: PublicationState) -> datetime.date | None:
        """Extract online publication date if state is Published."""
        return publication_state.online if isinstance(publication_state, Published) else None

    def _extract_print_date(self, publication_state: PublicationState) -> datetime.date | None:
        """Extract print publication date if state is Published."""
        return publication_state.print if isinstance(publication_state, Published) else None

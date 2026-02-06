"""DOI Import Service - Creates FundingRequests from DOI metadata."""

import datetime
from typing import TYPE_CHECKING

from coda.apps.journals import services as journal_services
from coda.apps.publishers import services as publisher_services
from coda.contexts.publication.dto.external_metadata import ExternalAuthor, ExternalJournal
from coda.contexts.publication.services.doi_client import DOIMetadataClient
from coda.domain.author import Author, Role
from coda.domain.contract import PublisherId
from coda.domain.errors import DomainError
from coda.domain.fundingrequest import FundingRequest, Payment, PaymentMethod
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    JournalId,
    License,
    Publication,
    PublicationId,
    Published,
)
from coda.domain.publication.publication import (
    InvalidLicenseType,
    PublicationState,
    Unpublished,
)
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr

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


DEFAULT_ESTIMATED_COST = Payment(
    amount=Money(0, Currency.EUR),
    method=PaymentMethod.Unknown,
)
DEFAULT_ESTIMATED_COST = Payment(
    amount=Money(0, Currency.EUR),
    method=PaymentMethod.Unknown,
)


class DOIImportService:
    """Import publication metadata from DOI and create a FundingRequest."""

    def __init__(self, doi_client: DOIMetadataClient) -> None:
        self.doi_client = doi_client

    def import_from_doi(self, doi: Doi) -> FundingRequest[Publication]:
        """Fetch metadata from DOI and create a FundingRequest with pre-populated publication."""
        self._ensure_doi_not_already_imported(doi)

        metadata = self.doi_client.fetch(doi)

        authors = self._process_authors(metadata.authors)
        journal_id = self._match_or_create_journal(metadata.journal, metadata.publisher)
        publication_state = self._map_publication_state(
            metadata.online_publication_date,
            metadata.print_publication_date,
        )

        publication = Publication.new(
            title=NonEmptyStr(metadata.title),
            journal=journal_id,
            relevant_authors=Authors(authors),
            license=self._map_license(metadata.license),
            publication_state=publication_state,
            links={doi},
        )

        return FundingRequest.new(
            publication=publication,
            estimated_cost=DEFAULT_ESTIMATED_COST,
        )

    def _ensure_doi_not_already_imported(self, doi: Doi) -> None:
        """Verify DOI has not been imported previously."""
        from coda.apps.publications.repositories import publication_repository

        existing_publication = publication_repository.find_by_doi(doi)
        if existing_publication:
            if existing_publication.id is None:
                raise InvalidMetadataError("Publication from database missing ID")
            raise DOIAlreadyImported(doi, existing_publication.id)

    def _process_authors(self, external_authors: list[ExternalAuthor]) -> list[Author]:
        """Convert external author metadata to domain Author objects."""
        authors = []

        for external_author in external_authors:
            normalized_name = self._normalize_author_name(
                external_author.name,
                external_author.affiliation,
                external_author.ror_id,
            )
            if normalized_name is None:
                continue

            authors.append(Author.new(name=NonEmptyStr(normalized_name), role=Role.CO_AUTHOR))

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
        self._validate_journal_metadata(external_journal, publisher_name)

        assert external_journal is not None
        assert external_journal.eissn is not None
        assert publisher_name is not None

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

    def _validate_journal_metadata(
        self, external_journal: ExternalJournal | None, publisher_name: str | None
    ) -> None:
        """Validate that journal metadata contains required fields."""
        if external_journal is None:
            raise InvalidMetadataError("Journal article missing journal metadata")
        if external_journal.eissn is None:
            raise InvalidMetadataError(f"Journal '{external_journal.title}' missing E-ISSN")
        if publisher_name is None:
            raise InvalidMetadataError("Journal missing publisher name")

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

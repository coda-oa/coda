"""DOI Import Service - Creates FundingRequests from DOI metadata."""

import datetime
from typing import TYPE_CHECKING

from coda.apps.journals import services as journal_services
from coda.apps.publishers import services as publisher_services
from coda.contexts.publication.dto.external_metadata import ExternalAuthor, ExternalJournal
from coda.contexts.publication.services.doi_client import DOIMetadataClient
from coda.domain.author import Author, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, Payment, PaymentMethod
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors, JournalId, License, Publication, Published
from coda.domain.publication.publication import (
    InvalidLicenseType,
    PublicationState,
    Unpublished,
)
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr

if TYPE_CHECKING:
    from coda.apps.publishers.models import Publisher

# Default estimated cost for imported publications (actual cost unknown at import time)
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

    def _process_authors(self, external_authors: list[ExternalAuthor]) -> list[Author]:
        """Process external authors, handling empty names and missing data.

        Rules:
        - Trim author names
        - If name is empty but has affiliation or ROR ID, use "Unknown"
        - If name is empty and no other data, skip the author entirely
        """
        authors = []

        for external_author in external_authors:
            trimmed_name = external_author.name.strip()
            has_other_data = (
                external_author.affiliation is not None or external_author.ror_id is not None
            )

            if trimmed_name:
                # Valid name - use it
                author_name = trimmed_name
            elif has_other_data:
                # Empty name but has affiliation or ROR ID - use "Unknown"
                author_name = "Unknown"
            else:
                # Empty name and no other data - skip this author
                continue

            authors.append(Author.new(name=NonEmptyStr(author_name), role=Role.CO_AUTHOR))

        return authors

    def _match_or_create_journal(
        self, external_journal: ExternalJournal | None, publisher_name: str | None
    ) -> JournalId:
        """Match journal by E-ISSN or create if not found."""
        assert external_journal is not None, "Journal articles must have journal metadata"
        assert external_journal.eissn is not None, "Journal must have E-ISSN"
        assert publisher_name is not None, "Journal must have publisher"

        # Convert string ISSN to domain type
        issn = Issn(external_journal.eissn)

        # Try to find existing journal by E-ISSN
        journal = journal_services.find_by_eissn(issn)
        if journal:
            return JournalId(journal.pk)

        # Journal doesn't exist - create it
        publisher = self._match_or_create_publisher(publisher_name)
        journal_id = journal_services.create(
            title=NonEmptyStr(external_journal.title),
            eissn=issn,
            publisher_id=PublisherId(publisher.pk),
        )
        return journal_id

    def _match_or_create_publisher(self, publisher_name: str) -> "Publisher":
        """Match publisher by name or create a new one."""
        # Find existing publisher
        publisher = publisher_services.find_by_name(publisher_name)
        if publisher:
            return publisher

        # Publisher doesn't exist - create it and fetch the model
        publisher_id = publisher_services.create(name=publisher_name)
        # Import here to avoid circular import at module level
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
        """Map publication dates to publication state.

        If at least one publication date exists, creates Published state.
        Otherwise, creates Unpublished state with Unknown status.
        """
        if online_date or print_date:
            return Published(online=online_date, print=print_date)
        return Unpublished()

"""Preview DTOs for DOI import - decoupled from creation DTOs.

These DTOs are designed for preview workflows where we want to display
imported publication metadata WITHOUT creating database entities (journals,
publishers, funding requests).

Key differences from creation DTOs:
- No database IDs required (uses names/identifiers instead)
- Single DOI string instead of links list (DOI imports always have exactly one DOI)
- ISBNs stored separately (will be combined with DOI into links set during conversion)
- No contracts field (not relevant for preview)
- No other_authors field (preview shows all authors equally)
- Minimal structure focused on what users need to see before confirming import
- Conversion methods accept missing data (IDs) as arguments to create full DTOs
"""

import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from coda.apps.authors.dto import AuthorDto
from coda.apps.dto import CodaBaseDto
from coda.apps.publications.dto import (
    ConceptDto,
    JournalDto,
    LinkDto,
    MonographDto,
    PublicationDto,
    PublicationMetaDto,
)
from coda.domain.contract import PublisherId
from coda.domain.publication.publication import JournalId
from coda.domain.string import NonEmptyStr


class PreviewPublicationMeta(CodaBaseDto):
    """Publication metadata for preview (subset of PublicationMetaDto)."""

    title: str
    publication_type: ConceptDto
    subject_area: ConceptDto
    license: str
    open_access_type: str
    publication_state: str
    online_publication_date: datetime.date | None
    print_publication_date: datetime.date | None


class PreviewJournal(CodaBaseDto):
    """Journal metadata for preview - no database ID required."""

    title: str
    issn: str | None = None
    eissn: str | None = None


class PreviewExternalFunding(CodaBaseDto):
    name: Annotated[str, AfterValidator(NonEmptyStr)]
    identifiers: list[str] = Field(default_factory=list)


class PreviewPublication(CodaBaseDto):
    meta: PreviewPublicationMeta
    doi: str
    authors: list[AuthorDto]
    publisher_name: str | None = None
    funders: list[PreviewExternalFunding] = Field(default_factory=list)


class PreviewArticle(PreviewPublication):
    """Article preview - uses journal metadata without requiring database ID.

    DOI imports always have exactly one DOI, stored as a string.
    """

    journal: PreviewJournal | None  # None when Crossref omits journal metadata
    publication_kind: Literal["journal_article"] = Field(default="journal_article")

    @property
    def warnings(self) -> list[str]:
        """Derive warnings from missing required fields (no stored state)."""
        result = []
        if self.journal is None:
            result.append(
                "Journal metadata is missing. Please select the journal for this article."
            )
        elif self.journal.eissn is None:
            result.append(
                f"Journal '{self.journal.title}' is missing an E-ISSN."
                " Please select the correct journal for this article."
            )
        return result

    def to_publication_dto(self, journal_id: JournalId) -> PublicationDto:
        """Convert to PublicationDto for creation, accepting database IDs.

        Args:
            journal_id: Database ID of the matched/created journal

        Returns:
            PublicationDto ready for creation with database entities
        """
        return PublicationDto(
            meta=PublicationMetaDto(
                title=self.meta.title,
                publication_type=self.meta.publication_type,
                subject_area=self.meta.subject_area,
                license=self.meta.license,
                open_access_type=self.meta.open_access_type,
                publication_state=self.meta.publication_state,
                online_publication_date=self.meta.online_publication_date,
                print_publication_date=self.meta.print_publication_date,
            ),
            journal=JournalDto(id=journal_id),
            links=[LinkDto(link_type="doi", link_value=self.doi)],
            relevant_authors=self.authors,
            other_authors=[],
            contracts=[],
        )


class PreviewMonograph(PreviewPublication):
    """Monograph preview - uses publisher name without requiring database ID.

    DOI imports always have exactly one DOI, stored as a string.
    ISBNs are stored separately (also a link type in the domain).
    """

    isbn: str | None
    publication_kind: Literal["monograph"] = Field(default="monograph")

    @property
    def warnings(self) -> list[str]:
        """Derive warnings from missing required fields (no stored state)."""
        result = []
        if self.publisher_name is None:
            result.append(
                "Publisher metadata is missing. Please select the publisher for this monograph."
            )
        return result

    def to_monograph_dto(self, publisher_id: PublisherId) -> MonographDto:
        """Convert to MonographDto for creation, accepting database IDs.

        Args:
            publisher_id: Database ID of the matched/created publisher

        Returns:
            MonographDto ready for creation with database entities
        """
        links = [LinkDto(link_type="doi", link_value=self.doi)]
        if self.isbn:
            links.append(LinkDto(link_type="ISBN", link_value=self.isbn))

        return MonographDto(
            meta=PublicationMetaDto(
                title=self.meta.title,
                publication_type=self.meta.publication_type,
                subject_area=self.meta.subject_area,
                license=self.meta.license,
                open_access_type=self.meta.open_access_type,
                publication_state=self.meta.publication_state,
                online_publication_date=self.meta.online_publication_date,
                print_publication_date=self.meta.print_publication_date,
            ),
            publisher=publisher_id,
            links=links,
            relevant_authors=self.authors,
            other_authors=[],
            contracts=[],
        )


class PreviewFundingRequest(CodaBaseDto):
    """Funding request preview - no database entities created.

    This DTO is used in preview workflows where users can see what will be
    imported before confirming. No journals, publishers, or funding requests
    are created until the user confirms the import.

    Note: Payment info is not included in preview - it's always created with
    default values (0.0 EUR, method unknown) when the user confirms the import.
    """

    publication: PreviewArticle | PreviewMonograph

    @property
    def warnings(self) -> list[str]:
        """Aggregate warnings from the nested publication DTO."""
        return self.publication.warnings

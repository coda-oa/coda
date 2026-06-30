"""External metadata DTOs - anti-corruption layer for Crossref/DataCite data."""

from __future__ import annotations

from collections.abc import Iterable
import datetime

from pydantic import BaseModel, Field

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


class ExternalAuthor(BaseModel):
    """Author information from external metadata sources."""

    name: str
    orcid: str | None = None
    affiliation: str | None = None


class ExternalJournal(BaseModel):
    """Journal information from external metadata sources."""

    title: str
    issn: str | None = None
    eissn: str | None = None


type FunderName = str
type ProjectId = str


class ExternalPublicationMetadata(BaseModel):
    """Publication metadata from external sources (Crossref, DataCite).

    This is our controlled data structure that isolates us from external API changes.
    The publication_type field stores the raw string from Crossref/DataCite:
    - Crossref uses kebab-case (e.g., 'journal-article', 'book', 'monograph')
    - DataCite uses PascalCase (e.g., 'JournalArticle', 'Book', 'BookChapter')

    Mapping to CODA's COAR vocabulary happens in a separate service layer.

    Publication dates:
    - online_publication_date: Date published online (Crossref: published-online)
    - print_publication_date: Date published in print (Crossref: published-print)
    """

    title: str
    authors: list[ExternalAuthor]
    publication_type: str  # Raw string from Crossref/DataCite
    journal: ExternalJournal | None = None
    publisher: str | None = None
    isbn: str | None = None
    license: str | None = None
    online_publication_date: datetime.date | None = None
    print_publication_date: datetime.date | None = None
    funders: list[ExternalFundingMetadata] = Field(default_factory=list)

    def override_journal(self, journal: Journal) -> ExternalPublicationMetadata:
        return self.model_copy(
            update={
                "journal": ExternalJournal(
                    title=journal.title,
                    issn=None,
                    eissn=journal.eissn,
                )
            }
        )

    def override_publisher(self, publisher: Publisher) -> ExternalPublicationMetadata:
        return self.model_copy(update={"publisher": publisher.name})

    def override_funding(
        self, names_and_projects: Iterable[tuple[FunderName, ProjectId]]
    ) -> ExternalPublicationMetadata:
        funding = [
            ExternalFundingMetadata(
                funder=ExternalFundingOrganisationMetadata(name=name),
                project_id=project_id,
            )
            for name, project_id in names_and_projects
        ]
        return self.model_copy(update={"funders": funding})


class ExternalFundingOrganisationMetadata(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)


class ExternalFundingMetadata(BaseModel):
    funder: ExternalFundingOrganisationMetadata
    project_id: str

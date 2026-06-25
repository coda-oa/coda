"""External metadata DTOs - anti-corruption layer for Crossref/DataCite data."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


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


class ExternalFundingOrganisationMetadata(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)


class ExternalFundingMetadata(BaseModel):
    funder: ExternalFundingOrganisationMetadata
    project_id: str

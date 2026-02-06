"""External metadata DTOs - anti-corruption layer for Crossref/DataCite data."""

import datetime
from dataclasses import dataclass


@dataclass
class ExternalAuthor:
    """Author information from external metadata sources."""

    name: str
    affiliation: str | None = None
    ror_id: str | None = None


@dataclass
class ExternalJournal:
    """Journal information from external metadata sources."""

    title: str
    issn: str | None = None
    eissn: str | None = None


@dataclass
class ExternalPublicationMetadata:
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
    license: str | None = None
    online_publication_date: datetime.date | None = None
    print_publication_date: datetime.date | None = None

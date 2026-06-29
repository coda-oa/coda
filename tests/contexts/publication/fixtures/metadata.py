"""Builders for ExternalPublicationMetadata test data.

Each function returns a fully constructed ExternalPublicationMetadata with
sensible defaults. Pass only the fields relevant to the test being written.
Client setup and DOI construction are intentionally left to the caller.
"""

import datetime
from typing import Literal

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalFundingMetadata,
    ExternalJournal,
    ExternalPublicationMetadata,
)

# Default journal constants reused across tests
NATURE_EISSN = "1476-4687"
NATURE_JOURNAL_TITLE = "Nature"


def article_metadata(
    *,
    title: str = "Test Article",
    authors: list[ExternalAuthor] | None = None,
    journal: ExternalJournal | Literal["unset"] | None = "unset",
    publisher: str | None = "Test Publisher",
    license: str | None = None,
    online_publication_date: datetime.date | None = datetime.date(2024, 1, 1),
    print_publication_date: datetime.date | None = None,
    publication_type: str = "journal-article",
    funding: list[ExternalFundingMetadata] | None = None,
) -> ExternalPublicationMetadata:
    """Build article metadata with sensible defaults.

    Args:
        title: Article title.
        authors: List of authors (defaults to single author "Test Author").
        journal: Journal metadata (defaults to Nature-like journal; pass None for no journal).
        publisher: Publisher name (defaults to "Test Publisher").
        license: License string (defaults to None).
        online_publication_date: Online publication date (defaults to 2024-01-01).
        print_publication_date: Print publication date (defaults to None).
        publication_type: Publication type string (defaults to "journal-article").

    Returns:
        ExternalPublicationMetadata for use in tests.
    """
    if authors is None:
        authors = [ExternalAuthor(name="Test Author")]

    if journal == "unset":
        journal = ExternalJournal(title=NATURE_JOURNAL_TITLE, eissn=NATURE_EISSN)

    return ExternalPublicationMetadata(
        title=title,
        authors=authors,
        publication_type=publication_type,
        journal=journal,
        publisher=publisher,
        license=license,
        online_publication_date=online_publication_date,
        print_publication_date=print_publication_date,
        funders=funding or [],
    )


def book_metadata(
    *,
    publisher: str | None = "Test Publisher",
    title: str = "Test Book",
    authors: list[ExternalAuthor] | None = None,
    isbn: str | None = None,
    journal: ExternalJournal | None = None,
    publication_type: str = "book",
    online_publication_date: datetime.date | None = None,
    print_publication_date: datetime.date | None = None,
    license: str | None = None,
    funding: list[ExternalFundingMetadata] | None = None,
) -> ExternalPublicationMetadata:
    """Build book/monograph metadata with sensible defaults.

    Args:
        publisher: Publisher name (defaults to "Test Publisher").
        title: Book title (defaults to "Test Book").
        authors: List of authors (defaults to single author "Test Author").
        isbn: ISBN string (defaults to None).
        journal: Journal metadata (defaults to None).
        publication_type: Publication type string (defaults to "book").
        online_publication_date: Online publication date (defaults to None).
        print_publication_date: Print publication date (defaults to None).
        license: License string (defaults to None).

    Returns:
        ExternalPublicationMetadata for use in tests.
    """
    if authors is None:
        authors = [ExternalAuthor(name="Test Author")]

    return ExternalPublicationMetadata(
        title=title,
        authors=authors,
        publication_type=publication_type,
        journal=journal,
        publisher=publisher,
        isbn=isbn,
        online_publication_date=online_publication_date,
        print_publication_date=print_publication_date,
        license=license,
        funders=funding or [],
    )

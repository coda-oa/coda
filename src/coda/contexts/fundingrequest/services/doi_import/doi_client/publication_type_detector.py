"""Crossref publication type detection.

This module contains logic specific to determining whether Crossref DOI metadata
represents a journal article or monograph (book). This separation allows for easy
addition of other DOI sources (DataCite, etc.) in the future.

Crossref defines 30+ publication types. We explicitly categorize the most common
types and fall back to ISBN/ISSN identifier-based detection for others.

Reference: https://api.crossref.org/types
"""

from typing import Literal

from coda.contexts.fundingrequest.dto.external_metadata import ExternalPublicationMetadata

CROSSREF_BOOK_TYPES = {
    "book",
    "monograph",
    "edited-book",
    "book-chapter",
    "book-section",
    "book-part",
    "book-track",
    "reference-book",
    "reference-entry",
    "dissertation",
}

CROSSREF_ARTICLE_TYPES = {
    "journal-article",
    "proceedings-article",
    "posted-content",
    "peer-review",
}

# NOTE: Other Crossref types (report, component, standard, database, dataset,
# grant, proceedings, journal, journal-volume, journal-issue, book-series,
# book-set, report-component, report-series, proceedings-series, other)
# are not explicitly categorized and fall through to identifier-based detection.


def detect_publication_type(
    metadata: ExternalPublicationMetadata,
) -> Literal["article", "monograph"]:
    """Detect whether Crossref metadata represents a journal article or monograph.

    Uses Crossref type field and ISBN/ISSN identifiers to determine publication type.

    Detection logic:
    1. Check explicit Crossref type against known book/article sets
    2. Fallback to ISBN presence → Monograph
    3. Fallback to ISSN presence (in journal metadata) → Article
    4. Default → Article (for completely unknown types)

    Args:
        metadata: External publication metadata from Crossref API

    Returns:
        Either "article" or "monograph"

    Example:
        >>> metadata = ExternalPublicationMetadata(
        ...     publication_type="book-chapter",
        ...     isbn="978-1-234-56789-0",
        ...     ...
        ... )
        >>> detect_publication_type(metadata)
        'monograph'
    """
    pub_type = metadata.publication_type.lower()

    if pub_type in CROSSREF_BOOK_TYPES:
        return "monograph"

    if pub_type in CROSSREF_ARTICLE_TYPES:
        return "article"

    if metadata.isbn:
        return "monograph"

    if metadata.journal and (metadata.journal.issn or metadata.journal.eissn):
        return "article"

    return "article"

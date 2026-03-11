"""Tests for DOI import service publication type detection.

This module tests the logic that determines whether a DOI metadata should be
imported as a Monograph or Publication (article) based on:
1. Crossref publication type
2. Presence of ISBN (indicates monograph)
3. Presence of ISSN (indicates article)
4. Default behavior for unknown types
"""

import pytest
from tests.contexts.publication.test_doi_import_service import (
    NATURE_EISSN,
    NATURE_JOURNAL_TITLE,
    make_article_metadata,
    make_book_metadata,
)

from coda.contexts.publication.dto.external_metadata import ExternalJournal
from coda.contexts.publication.dto.preview import PreviewArticle, PreviewMonograph
from coda.contexts.publication.services.doi_import_service import DOIImportService


@pytest.mark.django_db
@pytest.mark.parametrize(
    "publication_type",
    [
        "book",
        "monograph",
        "book-chapter",
        "book-section",
        "book-part",
        "book-track",
        "edited-book",
        "reference-book",
        "reference-entry",
        "dissertation",
    ],
)
def test__prepare_funding_request_dto__monograph_types__returns_preview_monograph(
    publication_type: str,
) -> None:
    """Crossref book-like types should return PreviewMonograph.

    Tests all 10 book-like Crossref types from https://api.crossref.org/types
    that should be detected as monographs.
    """
    # Arrange - No need to create publisher (preview doesn't create entities)
    fake_client, doi = make_book_metadata(
        publisher="Test Publisher", publication_type=publication_type
    )

    sut = DOIImportService(fake_client)

    # Act
    result = sut.fetch_doi_preview(doi)

    # Assert - Only verify publication type detection, not metadata parsing
    assert isinstance(result.publication, PreviewMonograph)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "publication_type",
    [
        "journal-article",
        "proceedings-article",
        "posted-content",
        "peer-review",
    ],
)
def test__prepare_funding_request_dto__article_types__returns_publication_dto(
    publication_type: str,
) -> None:
    """Crossref article-like types should return PreviewArticle.

    Tests all 4 article-like Crossref types from https://api.crossref.org/types
    that should be detected as journal articles.
    """
    # Arrange - No need to create journal (preview doesn't create entities)
    fake_client, doi = make_article_metadata(publication_type=publication_type)

    sut = DOIImportService(fake_client)

    # Act
    result = sut.fetch_doi_preview(doi)

    # Assert - Only verify publication type detection, not metadata parsing
    assert isinstance(result.publication, PreviewArticle)


@pytest.mark.django_db
def test__prepare_funding_request_dto__unknown_type_with_isbn__returns_monograph_dto() -> None:
    """Unknown Crossref type with ISBN should be detected as monograph."""
    # Arrange
    unrecognized_crossref_type = "unknown-type"
    test_isbn = "978-1-234-56789-0"

    fake_client, doi = make_book_metadata(
        publisher="Test Publisher",
        isbn=test_isbn,
        publication_type=unrecognized_crossref_type,
    )

    sut = DOIImportService(fake_client)

    # Act
    result = sut.fetch_doi_preview(doi)

    assert isinstance(result.publication, PreviewMonograph)


@pytest.mark.django_db
def test__prepare_funding_request_dto__unknown_type_with_issn__returns_publication_dto() -> None:
    """Unknown Crossref type with ISSN should be detected as article."""
    unrecognized_crossref_type = "unknown-type"

    fake_client, doi = make_article_metadata(
        publication_type=unrecognized_crossref_type,
        journal=ExternalJournal(title=NATURE_JOURNAL_TITLE, eissn=NATURE_EISSN),
    )

    sut = DOIImportService(fake_client)

    result = sut.fetch_doi_preview(doi)

    assert isinstance(result.publication, PreviewArticle)


@pytest.mark.django_db
def test__prepare_funding_request_dto__book_chapter_with_both_isbn_and_issn__returns_monograph_dto() -> (
    None
):
    """Book chapter with both ISBN and ISSN (series) should be detected as monograph.

    This is a common edge case: book chapters in numbered series have ISSN for the series
    and ISBN for the specific book. ISBN takes precedence.
    """
    # Arrange
    book_isbn = "978-1-234-56789-0"
    series_issn = "1234-5678"
    series_eissn = "9876-5432"

    fake_client, doi = make_book_metadata(
        publication_type="book-chapter",
        publisher="Test Publisher",
        isbn=book_isbn,
        journal=ExternalJournal(
            title="Test Journal Series",
            issn=series_issn,
            eissn=series_eissn,
        ),
    )

    sut = DOIImportService(fake_client)

    result = sut.fetch_doi_preview(doi)

    assert isinstance(result.publication, PreviewMonograph)


@pytest.mark.django_db
def test__prepare_funding_request_dto__unknown_type_no_identifiers__defaults_to_article() -> None:
    """Unknown type with no ISBN or ISSN should default to article with a warning.

    When Crossref returns an unrecognised publication type and there are no
    ISBN/ISSN identifiers to discriminate on, the service defaults to article.
    Because journal metadata is also absent in this scenario, the preview DTO
    carries a warning instead of raising – so the user can supply the journal.
    """
    # Arrange
    unrecognized_crossref_type = "unknown-type"

    fake_client, doi = make_article_metadata(
        publication_type=unrecognized_crossref_type,
        journal=None,
        publisher="Test Publisher",
    )

    sut = DOIImportService(fake_client)

    # Act
    result = sut.fetch_doi_preview(doi)

    # Assert - defaults to article with a warning (no exception raised)
    assert isinstance(result.publication, PreviewArticle)
    assert result.warnings, "Expected non-empty warnings for article defaulted without journal"

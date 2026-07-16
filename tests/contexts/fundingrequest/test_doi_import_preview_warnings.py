"""Tests for fetch_doi_preview behaviour when Crossref metadata is incomplete.

When journal (for articles) or publisher (for monographs) is absent from the
Crossref response, fetch_doi_preview must NOT raise – instead it returns a
PreviewFundingRequest whose .warnings list is non-empty so the caller can
present a fix form to the user.
"""

from coda.contexts.fundingrequest.services.doi_import.doi_client import InMemoryDOIMetadataClient
from tests.contexts.fundingrequest.fixtures import (
    article_metadata,
    book_metadata,
)

from coda.contexts.fundingrequest.dto.external_metadata import ExternalJournal
from coda.contexts.fundingrequest.dto.preview import PreviewArticle, PreviewMonograph
from coda.contexts.fundingrequest.services.doi_import._service import DOIImportService
from coda.domain.publication.links import Doi


def test__fetch_doi_preview__article_without_journal__returns_preview_with_warnings() -> None:
    """Article metadata missing journal → preview returned with non-empty warnings.

    Crossref sometimes omits journal metadata for journal articles.  Instead of
    raising InvalidMetadataError we should return a preview DTO that carries a
    warning so the user can supply the missing journal via the fix form.
    """
    doi = Doi("10.1234/test")
    fake_client = InMemoryDOIMetadataClient()
    fake_client.data[str(doi)] = article_metadata(journal=None, publisher=None)

    sut = DOIImportService(doi_client=fake_client)
    result = sut.fetch_doi_preview(doi)

    assert isinstance(result.publication, PreviewArticle)
    assert result.warnings, "Expected non-empty warnings for article missing journal"


def test__fetch_doi_preview__article_with_print_issn_only__returns_preview_with_warnings() -> None:
    """Article metadata with journal that has only a print ISSN (no E-ISSN) → preview with warnings.

    When Crossref returns a journal article with a journal that has a print ISSN
    but no E-ISSN, fetch_doi_preview must NOT raise – instead it returns a preview
    DTO with a non-empty warnings list so the user can supply the E-ISSN via the fix form.
    """
    doi = Doi("10.1234/test")
    fake_client = InMemoryDOIMetadataClient()
    fake_client.data[str(doi)] = article_metadata(
        journal=ExternalJournal(title="Print-Only Journal", issn="1234-5678", eissn=None),
    )

    sut = DOIImportService(doi_client=fake_client)
    result = sut.fetch_doi_preview(doi)

    assert isinstance(result.publication, PreviewArticle)
    assert result.warnings, "Expected non-empty warnings for article with print-ISSN-only journal"


def test__fetch_doi_preview__monograph_without_publisher__returns_preview_with_warnings() -> None:
    """Monograph metadata missing publisher → preview returned with non-empty warnings.

    Crossref sometimes omits publisher for monographs.  Instead of raising
    InvalidMetadataError we should return a preview DTO that carries a warning
    so the user can supply the missing publisher via the fix form.
    """
    doi = Doi("10.1234/test-book")
    fake_client = InMemoryDOIMetadataClient()
    fake_client.data[str(doi)] = book_metadata(publisher=None)

    sut = DOIImportService(doi_client=fake_client)
    result = sut.fetch_doi_preview(doi)

    assert isinstance(result.publication, PreviewMonograph)
    assert result.warnings, "Expected non-empty warnings for monograph missing publisher"

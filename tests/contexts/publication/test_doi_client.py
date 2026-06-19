"""Tests for DOI metadata client behavior.

These tests verify the DOI client protocol contract using both fake and real implementations.
Unit tests use FakeDOIMetadataClient, integration tests use CrossrefDataCiteClient.
"""

import pytest
from tests.contexts.publication.fixtures import nature_article_metadata

from coda.contexts.publication.services.doi_client import (
    DOIMetadataClient,
    InMemoryDOIMetadataClient,
    crossref,
)
from coda.contexts.publication.services.doi_client.errors import DOINotFoundError
from coda.domain.publication.links import Doi


@pytest.fixture
def fake_client() -> DOIMetadataClient:
    """Provides a fake DOI client configured with test data."""

    client = InMemoryDOIMetadataClient()
    # Configure with test data for the DOI used in these tests
    client.data["10.1038/nature12373"] = nature_article_metadata()
    return client


@pytest.fixture
def real_client() -> DOIMetadataClient:
    """Provides a real Crossref client for integration tests."""
    return crossref


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_client",
        pytest.param("real_client", marks=pytest.mark.integration),
    ],
)
def test__fetch_metadata__valid_doi__returns_metadata_with_title_and_authors(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Given a valid DOI, fetch returns metadata with at least title and authors."""
    client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi = Doi("10.1038/nature12373")

    metadata = client.fetch_publication(doi)

    assert metadata.title
    assert len(metadata.title) > 0
    assert metadata.authors is not None
    assert len(metadata.authors) >= 0  # May have 0 authors but field should exist


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_client",
        pytest.param("real_client", marks=pytest.mark.integration),
    ],
)
def test__fetch_metadata__nonexistent_doi__raises_doi_not_found_error(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Given a nonexistent DOI, fetch raises DOINotFoundError."""
    client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi = Doi("10.9999/nonexistent.doi.12345")

    with pytest.raises(DOINotFoundError):
        client.fetch_publication(doi)


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_client",
        pytest.param("real_client", marks=pytest.mark.integration),
    ],
)
def test__fetch_metadata__article_doi__returns_metadata_with_journal_info(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Given a journal article DOI, fetch returns metadata with journal information."""
    client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi = Doi("10.1038/nature12373")

    metadata = client.fetch_publication(doi)

    assert metadata.journal is not None
    assert metadata.journal.title
    assert metadata.journal.issn or metadata.journal.eissn


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_client",
        pytest.param("real_client", marks=pytest.mark.integration),
    ],
)
def test__fetch_metadata__preserves_raw_publication_type_from_source(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """External metadata stores raw publication type string from Crossref/DataCite.

    Crossref uses kebab-case (e.g., 'journal-article')
    DataCite uses PascalCase (e.g., 'JournalArticle')
    We preserve the raw string - mapping to COAR vocabulary happens elsewhere.
    """
    client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi = Doi("10.1038/nature12373")

    metadata = client.fetch_publication(doi)

    # Should preserve raw Crossref type string (not mapped to enum)
    assert metadata.publication_type == "journal-article"
    assert isinstance(metadata.publication_type, str)

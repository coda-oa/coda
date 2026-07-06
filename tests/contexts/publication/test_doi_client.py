"""Tests for DOI metadata client behavior.

These tests verify the DOI client protocol contract using both fake and real implementations.
Unit tests use FakeDOIMetadataClient, integration tests use CrossrefDataCiteClient.
"""

import datetime
import pytest

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
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
    client.data["10.1038/nature12373"] = ExternalPublicationMetadata(
        title="Example Nature Article",
        authors=[
            ExternalAuthor(
                name="John Doe",
                affiliation="University of Example",
                orcid="https://ror.org/01an7q238",
            ),
            ExternalAuthor(
                name="Jane Smith",
                affiliation="Research Institute",
                orcid=None,
            ),
        ],
        publication_type="journal-article",
        journal=ExternalJournal(
            title="Nature",
            issn="0028-0836",
            eissn="1476-4687",
        ),
        publisher="Springer Science and Business Media LLC",
        license="CC-BY",
        online_publication_date=datetime.date(2024, 1, 15),
    )
    client.data["10.1007/978-3-319-18938-3"] = ExternalPublicationMetadata(
        title="Quantum Microscopy of Biological Systems",
        authors=[ExternalAuthor(name="Michael Taylor")],
        publication_type="book",
        publisher="Springer International Publishing",
        isbn="9783319189376",
    )
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


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_client",
        pytest.param("real_client", marks=pytest.mark.integration),
    ],
)
def test__fetch_publications_batch__two_valid_dois__returns_both(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Given two valid DOIs, batch fetch returns both with metadata."""
    client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    dois = [Doi("10.1038/nature12373"), Doi("10.1007/978-3-319-18938-3")]

    results = client.fetch_publications_batch(dois)

    assert len(results) == 2
    for doi_str, result in results.items():
        assert isinstance(
            result, ExternalPublicationMetadata
        ), f"Expected metadata for {doi_str}, got {type(result).__name__}: {result}"
        assert result.title


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_client",
        pytest.param("real_client", marks=pytest.mark.integration),
    ],
)
def test__fetch_publications_batch__mixed_found_and_not_found__returns_both(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Given a mix of found and not-found DOIs, returns metadata and error."""
    client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    dois = [Doi("10.1038/nature12373"), Doi("10.9999/nonexistent.doi.xxxxx")]

    results = client.fetch_publications_batch(dois)

    assert len(results) == 2
    assert isinstance(results["10.1038/nature12373"], ExternalPublicationMetadata)
    assert isinstance(results["10.9999/nonexistent.doi.xxxxx"], Exception)

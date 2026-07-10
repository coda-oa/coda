import datetime
import json
from pathlib import Path

import pytest

from coda.contexts.fundingrequest.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client import InMemoryDOIMetadataClient
from coda.contexts.fundingrequest.services.doi_import.doi_client.errors import (
    DOIFetchError,
    DOINotFoundError,
)
from coda.domain.publication.links import Doi

ARTICLE_DOI = Doi("10.1038/s41586-020-2649-2")
BOOK_DOI = Doi("10.1007/978-3-319-18938-3")

ARTICLE_METADATA = ExternalPublicationMetadata(
    title="Array programming with NumPy",
    authors=[
        ExternalAuthor(
            name="Charles R. Harris", affiliation="SciPy", orcid="https://ror.org/02e2tgs60"
        )
    ],
    publication_type="journal-article",
    journal=ExternalJournal(title="Nature", issn="0028-0836", eissn="1476-4687"),
    publisher="Springer Science and Business Media LLC",
    license="https://creativecommons.org/licenses/by/4.0/",
    online_publication_date=datetime.date(2020, 9, 16),
)

BOOK_METADATA = ExternalPublicationMetadata(
    title="Machine Learning: A Probabilistic Perspective",
    authors=[ExternalAuthor(name="Kevin P. Murphy")],
    publication_type="book",
    publisher="MIT Press",
    isbn="9780262018029",
    print_publication_date=datetime.date(2012, 8, 24),
)


@pytest.fixture
def client() -> InMemoryDOIMetadataClient:
    c = InMemoryDOIMetadataClient()
    c.data[str(ARTICLE_DOI)] = ARTICLE_METADATA
    c.data[str(BOOK_DOI)] = BOOK_METADATA
    return c


def test__fetch__known_doi__returns_metadata(client: InMemoryDOIMetadataClient) -> None:
    result = client.fetch_publication(ARTICLE_DOI)
    assert result == ARTICLE_METADATA


def test__fetch__unknown_doi__raises_doi_not_found_error(client: InMemoryDOIMetadataClient) -> None:
    with pytest.raises(DOINotFoundError) as exc_info:
        client.fetch_publication(Doi("10.9999/unknown"))
    assert "not available in the demo dataset" in str(exc_info.value)


def test__fetch__configured_error__raises_doi_fetch_error(
    client: InMemoryDOIMetadataClient,
) -> None:
    client.configure_error(ARTICLE_DOI, "rate_limit")
    with pytest.raises(DOIFetchError) as exc_info:
        client.fetch_publication(ARTICLE_DOI)
    assert "Rate limit exceeded" in str(exc_info.value)


def test__from_json__valid_fixture__loads_and_validates_all_entries(tmp_path: Path) -> None:
    fixture = {
        str(ARTICLE_DOI): ARTICLE_METADATA.model_dump(mode="json"),
        str(BOOK_DOI): BOOK_METADATA.model_dump(mode="json"),
    }
    fixture_file = tmp_path / "demo_dois.json"
    fixture_file.write_text(json.dumps(fixture))

    loaded_client = InMemoryDOIMetadataClient.from_json(fixture_file)

    assert loaded_client.fetch_publication(ARTICLE_DOI) == ARTICLE_METADATA
    assert loaded_client.fetch_publication(BOOK_DOI) == BOOK_METADATA


def test__from_json__invalid_metadata__raises_validation_error(tmp_path: Path) -> None:
    from pydantic import ValidationError

    fixture = {
        "10.1038/bad": {"title": "Missing required fields"}
    }  # missing authors, publication_type
    fixture_file = tmp_path / "demo_dois.json"
    fixture_file.write_text(json.dumps(fixture))

    with pytest.raises(ValidationError):
        InMemoryDOIMetadataClient.from_json(fixture_file)


def test__from_json__malformed_json__raises_decode_error(tmp_path: Path) -> None:
    fixture_file = tmp_path / "demo_dois.json"
    fixture_file.write_text("not valid json {{{")

    with pytest.raises(json.JSONDecodeError):
        InMemoryDOIMetadataClient.from_json(fixture_file)

"""Tests for DOI preview page behaviour when Crossref metadata is incomplete.

When journal (for articles) or publisher (for monographs) is absent from the
Crossref response, the preview page must still render (HTTP 200) and show:
- a human-readable warning banner
- the appropriate fix form rendered inline so the user can supply the data

Once the user applies an override the warning must disappear.
"""

import pytest
from django.test import Client

from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
)
from coda.apps.journals.models import Journal
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalPublicationMetadata,
)
from coda.domain.publication.links import Doi
from tests.contexts.publication.fixtures.doi_client import FakeDOIMetadataClient
from tests.fundingrequests.test_doi_import_preview import (
    get_session_key,
    submit_for_preview,
    submit_type_change,
)


@pytest.fixture
def fake_doi_client() -> FakeDOIMetadataClient:
    return FakeDOIMetadataClient()


@pytest.fixture(autouse=True)
def inject_fake_doi_client(fake_doi_client: FakeDOIMetadataClient) -> None:
    DOIImportInputView.doi_client = fake_doi_client
    DOIPreviewDetailView.doi_client = fake_doi_client
    DOIPreviewSaveView.doi_client = fake_doi_client


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_preview_page__article_without_journal__shows_warning_and_fix_form(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """Article missing journal → preview shows 200 with warning banner and article fix form.

    When Crossref omits journal metadata for a journal-article, the preview page
    must still render (HTTP 200) and must:
    - include a human-readable warning message
    - render the article fix form inline so the user can supply the journal
    """
    doi_str = "10.1234/no-journal.article"
    doi = Doi(doi_str)
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Article Without Journal",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=None,
        publisher=None,
        isbn=None,
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    preview_response = client.get(preview_url)

    assert preview_response.status_code == 200
    content = preview_response.content.decode()
    assert "Journal metadata is missing" in content
    assert "Select Journal" in content
    assert "Apply Change to Article" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_preview_page__monograph_without_publisher__shows_warning_and_fix_form(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """Monograph missing publisher → preview shows 200 with warning banner and monograph fix form.

    When Crossref omits publisher metadata for a monograph, the preview page
    must still render (HTTP 200) and must:
    - include a human-readable warning message
    - render the monograph fix form inline so the user can supply the publisher
    """
    doi_str = "10.1234/no-publisher.book"
    doi = Doi(doi_str)
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Book Without Publisher",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="book",
        journal=None,
        publisher=None,
        isbn=None,
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    preview_response = client.get(preview_url)

    assert preview_response.status_code == 200
    content = preview_response.content.decode()
    assert "Publisher metadata is missing" in content
    assert "Select Publisher" in content
    assert "Apply Change to Monograph" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_preview_page__override_applied__no_warnings(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
    test_journal: Journal,
) -> None:
    """After journal override applied, warnings are gone from preview page.

    Once the user supplies a journal via the fix form, the preview page should
    render without any warning banner.
    """
    doi_str = "10.1234/no-journal.override"
    doi = Doi(doi_str)
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Article Without Journal",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=None,
        publisher=None,
        isbn=None,
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    submit_type_change(client, session_key, "article", journal=test_journal.pk)

    preview_url = response["Location"]
    preview_response = client.get(preview_url)

    assert preview_response.status_code == 200
    content = preview_response.content.decode()
    assert "Journal metadata is missing" not in content

"""Tests for DOI import preview workflow.

User journey:
1. User enters DOI on input form
2. System fetches metadata and shows preview (NOT persisted to DB)
3. User reviews preview
4. User clicks "Save" → System persists to database
5. User redirected to funding request detail page
"""

import datetime
from typing import Any, Literal, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
)
from coda.apps.journals.models import Journal
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.domain.author import Author, AuthorNames, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, NoContact, Payment, PaymentMethod
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    JournalId,
    License,
    Monograph,
    OpenAccessType,
    Publication,
    Published,
)
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import UnknownConcept
from tests import modelfactory
from tests.contexts.publication.fixtures.doi_client import FakeDOIMetadataClient
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq


def get_session_key(response: HttpResponse) -> str:
    return response["Location"].split("/")[-2]


def submit_for_preview(client: Client, doi_str: str) -> HttpResponse:
    return cast(
        HttpResponse,
        client.post(
            reverse("fundingrequests:doi_import_input"),
            data={"doi": doi_str},
        ),
    )


def save_doi_import(client: Client, session_key: str) -> HttpResponse:
    return cast(
        HttpResponse,
        client.post(
            reverse("fundingrequests:doi_preview_save", kwargs={"session_key": session_key})
        ),
    )


def build_expected_fundingrequest(
    doi: Doi,
    journal_id: JournalId,
    title: str = "Test DOI Preview Article",
    authors: list[Author] | None = None,
    license: License = License.Unknown,
    publication_date: datetime.date | None = None,
) -> FundingRequest[Publication]:
    """Build expected FundingRequest domain object.

    This defines WHAT we expect the system to create. The fake DOI client
    will be configured separately to return metadata that produces this result.

    Args:
        doi: DOI for the publication
        journal_id: Journal ID to use
        title: Publication title
        authors: List of authors (defaults to single test author)
        license: Publication license
        publication_date: Online publication date

    Returns:
        Expected FundingRequest domain object
    """
    if authors is None:
        authors = [
            Author.new(
                name=NonEmptyStr("Test Author"),
                email="",
                orcid=None,
                affiliation=None,
                role=Role.CO_AUTHOR,
            )
        ]

    publication_state = Published(online=publication_date, print=None)

    publication = Publication.new(
        title=NonEmptyStr(title),
        journal=journal_id,
        relevant_authors=authors,
        other_authors=AuthorNames(),
        license=license,
        subject_area=UnknownConcept,
        publication_type=UnknownConcept,
        open_access_type=OpenAccessType.Unknown,
        publication_state=publication_state,
        links={doi},
    )
    publication.contracts = ()

    payment = Payment(
        amount=Money("0.00", Currency.EUR),
        method=PaymentMethod.Unknown,
        external_costsplitting=None,
    )

    return FundingRequest.new(
        publication=publication,
        estimated_cost=payment,
        external_funding=[],
        extra_contact=NoContact,
        request_remarks="",
    )


def configure_fake_client_from_expected(
    fake_client: FakeDOIMetadataClient,
    doi: Doi,
    expected_fr: FundingRequest[Publication],
    journal_title: str,
    journal_eissn: str,
    publisher_name: str,
) -> None:
    """Configure fake DOI client to return metadata matching expected FundingRequest.

    This reverses the mapping: given what we expect, configure the client
    to return metadata that will produce that result when imported.

    Args:
        fake_client: Fake client to configure
        doi: DOI string
        expected_fr: Expected FundingRequest with publication
        journal_title: Journal title for metadata
        journal_eissn: Journal E-ISSN for metadata
        publisher_name: Publisher name for metadata
    """
    publication = expected_fr.publication

    # Extract authors from publication
    external_authors = [
        ExternalAuthor(name=str(author.name)) for author in publication.relevant_authors
    ]

    # Extract publication date
    online_date = None
    if isinstance(publication.publication_state, Published):
        online_date = publication.publication_state.online

    # Extract license
    license_str = None if publication.license == License.Unknown else publication.license.value

    # Build external metadata
    metadata = ExternalPublicationMetadata(
        title=str(publication.title),
        authors=external_authors,
        publication_type="journal-article",
        journal=ExternalJournal(
            title=journal_title,
            eissn=journal_eissn,
        ),
        publisher=publisher_name,
        license=license_str,
        online_publication_date=online_date,
        print_publication_date=None,
    )

    # Configure fake client
    fake_client.data[str(doi)] = metadata


@pytest.fixture
def fake_doi_client() -> FakeDOIMetadataClient:
    """Fake DOI client that will be configured per-test with expected data."""
    return FakeDOIMetadataClient()


@pytest.fixture(autouse=True)
def inject_fake_doi_client(fake_doi_client: FakeDOIMetadataClient) -> None:
    """Inject fake DOI client into views via dependency injection."""
    DOIImportInputView.doi_client = fake_doi_client
    DOIPreviewDetailView.doi_client = fake_doi_client
    DOIPreviewSaveView.doi_client = fake_doi_client


@pytest.fixture
def expected_fundingrequest(
    test_journal: tuple[JournalId, str, str, str],
    fake_doi_client: FakeDOIMetadataClient,
) -> FundingRequest[Publication]:
    """Build expected FundingRequest and configure fake client to produce it."""
    journal_id, journal_title, journal_eissn, publisher_name = test_journal
    doi_str = "10.1234/preview.test"
    doi = Doi(doi_str)

    # Build expected FundingRequest (what we WANT)
    expected = build_expected_fundingrequest(
        doi=doi,
        journal_id=journal_id,
        title="Test DOI Preview Article",
        publication_date=datetime.date(2024, 1, 1),
    )

    # Configure fake client to return metadata that produces this result
    configure_fake_client_from_expected(
        fake_client=fake_doi_client,
        doi=doi,
        expected_fr=expected,
        journal_title=journal_title,
        journal_eissn=journal_eissn,
        publisher_name=publisher_name,
    )

    return expected


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_doi_input_redirects_to_preview_page(client: Client) -> None:
    """User submits DOI on input form and system redirects to preview page."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)

    assert response.status_code == 302
    preview_url = response["Location"]
    assert "/doi-preview/" in preview_url


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_preview_page_shows_doi_metadata(client: Client) -> None:
    """Preview page displays DOI metadata after submission."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]

    preview_response = client.get(preview_url)

    assert preview_response.status_code == 200
    assert b"Test DOI Preview Article" in preview_response.content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_preview_does_not_persist_until_saved(client: Client) -> None:
    """Preview remains session-only until user clicks save."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    client.get(preview_url)

    assert repository.first() is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_saving_preview_creates_correct_fundingrequest(
    client: Client,
    expected_fundingrequest: FundingRequest[Publication],
) -> None:
    """Saving preview creates FundingRequest in database with correct metadata."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)

    save_doi_import(client, get_session_key(response))

    actual = repository.first()
    assert_fundingrequest_eq(actual, expected_fundingrequest)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test__doi_imported__save_doi_again__fails(client: Client) -> None:
    doi_str = "10.1234/preview.test"

    response = submit_for_preview(client, doi_str)
    save_doi_import(client, get_session_key(response))

    response = submit_for_preview(client, doi_str)
    save_doi_import(client, get_session_key(response))

    assert len(repository.all()) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_saving_preview_redirects_to_detail_page(client: Client) -> None:
    """Saving preview redirects to FundingRequest detail page."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)

    save_response = save_doi_import(client, get_session_key(response))

    fr = repository.first()
    assert fr is not None
    assertRedirects(save_response, reverse("fundingrequests:detail", kwargs={"pk": fr.id}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_multiple_previews_can_coexist(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
    test_journal: tuple[JournalId, str, str, str],
) -> None:
    """Multiple preview sessions can coexist; saving one does not affect others."""
    journal_id, journal_title, journal_eissn, publisher_name = test_journal

    doi1 = Doi("10.1234/preview.test")
    expected1 = build_expected_fundingrequest(
        doi=doi1,
        journal_id=journal_id,
        title="Test DOI Preview Article",
        publication_date=datetime.date(2024, 1, 1),
    )
    configure_fake_client_from_expected(
        fake_client=fake_doi_client,
        doi=doi1,
        expected_fr=expected1,
        journal_title=journal_title,
        journal_eissn=journal_eissn,
        publisher_name=publisher_name,
    )

    doi2 = Doi("10.5678/another.article")
    expected2 = build_expected_fundingrequest(
        doi=doi2,
        journal_id=journal_id,
        title="Another Test Article",
        publication_date=datetime.date(2024, 2, 1),
    )
    configure_fake_client_from_expected(
        fake_client=fake_doi_client,
        doi=doi2,
        expected_fr=expected2,
        journal_title=journal_title,
        journal_eissn=journal_eissn,
        publisher_name=publisher_name,
    )

    response1 = submit_for_preview(client, str(doi1))
    preview_url1 = response1["Location"]
    session_key1 = get_session_key(response1)

    response2 = submit_for_preview(client, str(doi2))
    preview_url2 = response2["Location"]

    preview1 = client.get(preview_url1)
    preview2 = client.get(preview_url2)
    assert preview1.status_code == 200
    assert preview2.status_code == 200

    save_doi_import(client, session_key1)

    assert len(repository.all()) == 1

    preview2_again = client.get(preview_url2)
    assert preview2_again.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_saving_preview_cleans_up_session(client: Client) -> None:
    """Saving preview removes session data and makes preview inaccessible."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    session_key = get_session_key(response)

    save_doi_import(client, session_key)

    assert session_key not in client.session
    preview_after_save = client.get(preview_url)
    assert preview_after_save.status_code == 404


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_doi_input_stores_original_metadata_and_publication_type(client: Client) -> None:
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    session_data = client.session[session_key]

    assert "doi" in session_data
    assert "original_metadata" in session_data
    assert "publication_type" in session_data
    assert "active_preview" not in session_data
    assert "original_preview" not in session_data


def load_type_form(
    client: Client, session_key: str, pub_type: "Literal['article', 'monograph']"
) -> HttpResponse:
    """Helper to load HTMX type change form."""
    return cast(
        HttpResponse,
        client.get(
            reverse(
                "fundingrequests:doi_preview_load_type_form",
                kwargs={"session_key": session_key},
            ),
            data={"publication_type": pub_type},
        ),
    )


def submit_type_change(
    client: Client,
    session_key: str,
    pub_type: "Literal['article', 'monograph']",
    **kwargs: Any,
) -> HttpResponse:
    """Helper to submit type change form."""
    data = {"publication_type": pub_type, **kwargs}
    return cast(
        HttpResponse,
        client.post(
            reverse(
                "fundingrequests:doi_preview_apply_type_change",
                kwargs={"session_key": session_key},
            ),
            data=data,
        ),
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_load_article_form_shows_journal_search(client: Client) -> None:
    """HTMX endpoint should return article form partial with journal search."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "article")

    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "journal_title" in content
    assert "Search" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_load_monograph_form_shows_prefilled_publisher(client: Client) -> None:
    """HTMX endpoint for monograph form should pre-fill publisher from original metadata."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "monograph")

    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "publisher_name" in content
    # Should pre-fill publisher from original_metadata["publisher"]
    assert "Test Publisher" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_submit_type_change_to_monograph_stores_publisher_id_in_session(
    client: Client,
) -> None:
    """Submitting monograph form with publisher should store publisher_id in session."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    publisher = modelfactory.publisher(name="Test Publisher")

    change_response = submit_type_change(client, session_key, "monograph", publisher=publisher.pk)

    assert change_response.status_code == 200
    assert f"/doi-preview/{session_key}/" in change_response["HX-Redirect"]

    session_data = client.session[session_key]
    assert session_data["publication_type"] == "monograph"
    assert session_data["publisher_id"] == publisher.pk


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_submit_type_change_to_article_stores_journal_id_in_session(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
    test_journal: tuple[JournalId, str, str, str],
) -> None:
    """Submitting article form with journal should store journal_id in session."""
    journal_id, journal_title, journal_eissn, publisher_name = test_journal

    # Start with a monograph DOI
    doi_str = "10.1234/book.test"
    doi = Doi(doi_str)
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Book",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="book",
        journal=None,
        publisher=publisher_name,
        isbn="978-3-16-148410-0",
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    journal = Journal.objects.get(pk=int(journal_id))

    change_response = submit_type_change(client, session_key, "article", journal=journal.pk)

    assert change_response.status_code == 200
    assert f"/doi-preview/{session_key}/" in change_response["HX-Redirect"]

    session_data = client.session[session_key]
    assert session_data["publication_type"] == "article"
    assert session_data["journal_id"] == journal.pk


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_preview_page_shows_type_selector_with_htmx(client: Client) -> None:
    """Preview page should show publication type selector with HTMX attributes."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    preview_response = client.get(preview_url)
    content = preview_response.content.decode()

    assert 'name="publication_type"' in content
    assert 'value="article"' in content
    assert 'value="monograph"' in content
    assert "hx-get" in content
    assert "load-type-form" in content


def reset_type(client: Client, session_key: str) -> HttpResponse:
    """Helper to call the reset-type HTMX endpoint."""
    return cast(
        HttpResponse,
        client.post(
            reverse(
                "fundingrequests:doi_preview_reset_type",
                kwargs={"session_key": session_key},
            ),
        ),
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_submit_type_change_monograph_without_publisher_shows_inline_error(
    client: Client,
) -> None:
    """Submitting monograph form without selecting a publisher returns partial with error."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    change_response = submit_type_change(client, session_key, "monograph")

    assert change_response.status_code == 200
    assert "HX-Redirect" not in change_response
    content = change_response.content.decode()
    assert "Please select a publisher before applying." in content
    # Session should not be modified — type stays as originally detected
    session_data = client.session[session_key]
    assert "publisher_id" not in session_data


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_submit_type_change_article_without_journal_shows_inline_error(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """Submitting article form without selecting a journal returns partial with error."""
    doi_str = "10.1234/book.no-journal"
    doi = Doi(doi_str)
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Book",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="book",
        journal=None,
        publisher="Test Publisher",
        isbn="978-3-16-148410-0",
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    change_response = submit_type_change(client, session_key, "article")

    assert change_response.status_code == 200
    assert "HX-Redirect" not in change_response
    content = change_response.content.decode()
    assert "Please select a journal before applying." in content
    session_data = client.session[session_key]
    assert "journal_id" not in session_data


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_reset_type_clears_override_and_restores_original_type(
    client: Client,
) -> None:
    """Reset endpoint clears override and restores the auto-detected publication type."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    # Apply monograph override
    publisher = modelfactory.publisher(name="Test Publisher")
    submit_type_change(client, session_key, "monograph", publisher=publisher.pk)

    # Verify override is stored
    session_data = client.session[session_key]
    assert session_data["publication_type"] == "monograph"
    assert "publisher_id" in session_data

    # Reset to original
    reset_response = reset_type(client, session_key)

    assert reset_response.status_code == 200
    assert f"/doi-preview/{session_key}/" in reset_response["HX-Redirect"]

    session_data = client.session[session_key]
    assert session_data["publication_type"] == "article"  # original auto-detected type
    assert "publisher_id" not in session_data
    assert "journal_id" not in session_data


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_override_article_to_monograph_and_save(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """Full workflow: article DOI → override to monograph → save creates Monograph."""
    doi_str = "10.1234/override.test"
    doi = Doi(doi_str)

    publisher = modelfactory.publisher(name="Springer")
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Article",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=ExternalJournal(title="Nature", eissn="1476-4687"),
        publisher="Springer",
        isbn=None,
        license=None,
        online_publication_date=datetime.date(2024, 1, 1),
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    submit_type_change(client, session_key, "monograph", publisher=publisher.pk)
    save_doi_import(client, session_key)

    fr = repository.first()
    assert fr is not None
    assert isinstance(fr.publication, Monograph)
    assert fr.publication.publisher == PublisherId(publisher.pk)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_override_monograph_to_article_and_save(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
    test_journal: tuple[JournalId, str, str, str],
) -> None:
    """Full workflow: monograph DOI → override to article → save creates Publication."""
    journal_id, journal_title, journal_eissn, publisher_name = test_journal
    doi_str = "10.1234/book.override"
    doi = Doi(doi_str)

    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Book",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="book",
        journal=None,
        publisher=publisher_name,
        isbn="978-3-16-148410-0",
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    journal = Journal.objects.get(pk=int(journal_id))
    submit_type_change(client, session_key, "article", journal=journal.pk)
    save_doi_import(client, session_key)

    fr = repository.first()
    assert fr is not None
    assert isinstance(fr.publication, Publication)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_doi_input_form_displays_correctly(client: Client) -> None:
    """DOI import input page displays form with DOI field and submit button."""
    response = client.get(reverse("fundingrequests:doi_import_input"))

    assert response.status_code == 200
    assert b"Enter DOI" in response.content or b"DOI" in response.content
    assert b'type="text"' in response.content
    assert b'name="doi"' in response.content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_doi_input_handles_fetch_error(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """DOI metadata fetch failure displays error message without redirect."""
    test_doi = Doi("10.1234/broken.doi")
    fake_doi_client.configure_error(test_doi, "network")

    response = submit_for_preview(client, test_doi.value())

    assert response.status_code == 200
    assert b"Import Error" in response.content or b"error" in response.content.lower()
    assert b"Failed to import DOI" in response.content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_doi_input_handles_not_found_error(client: Client) -> None:
    """Nonexistent DOI displays error message."""
    not_found_doi = "10.1234/nonexistent.doi"
    response = submit_for_preview(client, not_found_doi)

    assert response.status_code == 200
    assert b"Import Error" in response.content or b"error" in response.content.lower()
    assert b"Failed to import DOI" in response.content

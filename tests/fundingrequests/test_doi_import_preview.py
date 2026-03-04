"""Tests for DOI import preview workflow.

User journey:
1. User enters DOI on input form
2. System fetches metadata and shows preview (NOT persisted to DB)
3. User reviews preview
4. User clicks "Save" → System persists to database
5. User redirected to funding request detail page
"""

import datetime
from typing import cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView, DOIPreviewSaveView
from coda.apps.journals import services as journal_services
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.domain.author import Author, AuthorNames, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, NoContact, Payment, PaymentMethod
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    JournalId,
    License,
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
    DOIPreviewSaveView.doi_client = fake_doi_client


@pytest.fixture
def test_journal() -> tuple[JournalId, str, str, str]:
    """Create test journal and return (id, title, eissn, publisher_name)."""
    publisher_name = "Test Publisher"
    journal_title = "Nature"
    journal_eissn = "1476-4687"

    publisher_id = PublisherId(modelfactory.publisher(name=publisher_name).pk)
    journal_id = journal_services.create(
        title=NonEmptyStr(journal_title),
        eissn=Issn(journal_eissn),
        publisher_id=publisher_id,
    )

    return journal_id, journal_title, journal_eissn, publisher_name


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
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_preview_does_not_persist_to_database(client: Client) -> None:
    """Preview does not create FundingRequest in database until saved."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    client.get(preview_url)

    assert repository.first() is None


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
@pytest.mark.usefixtures("logged_in", "fake_doi_client")
def test_doi_input_handles_not_found_error(client: Client) -> None:
    """Nonexistent DOI displays error message."""
    not_found_doi = "10.1234/nonexistent.doi"
    response = submit_for_preview(client, not_found_doi)

    assert response.status_code == 200
    assert b"Import Error" in response.content or b"error" in response.content.lower()
    assert b"Failed to import DOI" in response.content

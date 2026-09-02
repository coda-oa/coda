"""Tests for DOI import preview workflow.

User journey:
1. User enters DOI on input form
2. System fetches metadata and shows preview (NOT persisted to DB)
3. User reviews preview
4. User clicks "Save" → System persists to database
5. User redirected to funding request detail page
"""

import datetime
from collections.abc import Generator
from typing import Any, Literal, cast

import pytest
from django.contrib.messages import get_messages
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
from coda.apps.journals import services as journal_services
from coda.contexts.fundingrequest.services.doi_import.doi_client import crossref
from coda.contexts.fundingrequest.services.doi_import.doi_client._inmemory import (
    InMemoryDOIMetadataClient,
)
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest.fundingrequest import FundingRequestId
from coda.domain.issn import Issn
from coda.domain.publication import Monograph, Publication
from coda.domain.string import NonEmptyStr
from tests import modelfactory
from tests.contexts.fundingrequest.fixtures import ArticleScenario, BookScenario
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


@pytest.fixture
def fake_doi_client() -> InMemoryDOIMetadataClient:
    """Fake DOI client that will be configured per-test with expected data."""
    return InMemoryDOIMetadataClient()


@pytest.fixture(autouse=True)
def inject_fake_doi_client(fake_doi_client: InMemoryDOIMetadataClient) -> Generator[None]:
    """Inject fake DOI client into views via dependency injection."""
    DOIImportInputView.doi_client = fake_doi_client
    DOIPreviewDetailView.doi_client = fake_doi_client
    DOIPreviewSaveView.doi_client = fake_doi_client

    yield

    DOIImportInputView.doi_client = crossref
    DOIPreviewDetailView.doi_client = crossref
    DOIPreviewSaveView.doi_client = crossref


@pytest.fixture
def scenario(fake_doi_client: InMemoryDOIMetadataClient) -> ArticleScenario:
    return ArticleScenario(fake_doi_client).setup_db()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_doi_input_redirects_to_preview_page(client: Client, scenario: ArticleScenario) -> None:
    """User submits DOI on input form and system redirects to preview page."""
    response = submit_for_preview(client, scenario.doi.value())

    assert response.status_code == 302
    preview_url = response["Location"]
    assert "/doi-preview/" in preview_url


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_preview_page_shows_doi_metadata(client: Client, scenario: ArticleScenario) -> None:
    """Preview page displays DOI metadata after submission."""
    response = submit_for_preview(client, scenario.doi.value())
    preview_url = response["Location"]

    preview_response = client.get(preview_url)

    publication_title = scenario.get_expected_fundingrequest().publication.title.encode()
    assert preview_response.status_code == 200
    assert publication_title in preview_response.content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_preview_does_not_persist_until_saved(client: Client, scenario: ArticleScenario) -> None:
    """Preview remains session-only until user clicks save."""
    response = submit_for_preview(client, scenario.doi.value())
    preview_url = response["Location"]
    client.get(preview_url)

    assert repository.first() is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_saving_preview_creates_correct_fundingrequest(
    client: Client, scenario: ArticleScenario
) -> None:
    """Saving preview creates FundingRequest in database with correct metadata."""
    response = submit_for_preview(client, scenario.doi.value())

    save_doi_import(client, get_session_key(response))

    actual = repository.first()
    assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__doi_imported__save_doi_again__fails(client: Client, scenario: ArticleScenario) -> None:
    response = submit_for_preview(client, scenario.doi.value())
    save_doi_import(client, get_session_key(response))

    response = submit_for_preview(client, scenario.doi.value())
    save_doi_import(client, get_session_key(response))

    assert len(repository.all()) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_saving_preview_redirects_to_detail_page(client: Client, scenario: ArticleScenario) -> None:
    """Saving preview redirects to FundingRequest detail page."""
    response = submit_for_preview(client, scenario.doi.value())

    save_response = save_doi_import(client, get_session_key(response))

    fr = repository.first()
    assert fr is not None
    assertRedirects(save_response, reverse("fundingrequests:detail", kwargs={"pk": fr.id}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_multiple_previews_can_coexist(
    client: Client,
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """Multiple preview sessions can coexist; saving one does not affect others."""
    _ = (
        ArticleScenario(fake_doi_client, "10.1234/preview.test")
        .with_title("Test DOI Preview Article")
        .with_online_date(datetime.date(2024, 1, 1))
        .setup_db()
    )

    _ = (
        ArticleScenario(fake_doi_client, "10.5678/another.article")
        .with_title("Another Test Article")
        .with_online_date(datetime.date(2024, 2, 1))
        .setup_client()
    )

    response1 = submit_for_preview(client, "10.1234/preview.test")
    preview_url1 = response1["Location"]
    session_key1 = get_session_key(response1)

    response2 = submit_for_preview(client, "10.5678/another.article")
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
@pytest.mark.usefixtures("logged_in")
def test_saving_preview_cleans_up_session(client: Client, scenario: ArticleScenario) -> None:
    """Saving preview removes session data and makes preview inaccessible."""
    response = submit_for_preview(client, scenario.doi.value())
    preview_url = response["Location"]
    session_key = get_session_key(response)

    save_doi_import(client, session_key)

    assert session_key not in client.session
    preview_after_save = client.get(preview_url)
    assert preview_after_save.status_code == 404


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_doi_input_stores_original_metadata_and_publication_type(
    client: Client, scenario: ArticleScenario
) -> None:
    response = submit_for_preview(client, scenario.doi.value())
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
@pytest.mark.usefixtures("logged_in")
def test_load_article_form_shows_journal_search(client: Client, scenario: ArticleScenario) -> None:
    """HTMX endpoint should return article form partial with journal search."""
    response = submit_for_preview(client, scenario.doi.value())
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "article")

    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "journal_title" in content
    assert "Search" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_load_article_form_search_button_uses_find_journal_endpoint(
    client: Client, scenario: ArticleScenario
) -> None:
    """Article type-change form search button should use wizard_find_journal endpoint."""
    response = submit_for_preview(client, scenario.doi.value())
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "article")

    content = form_response.content.decode()
    assert reverse("fundingrequests:wizard_find_journal") in content
    assert 'hx-target="#journal-search-results"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_load_article_form_journal_search_requests_stripped_row_template(
    client: Client, scenario: ArticleScenario
) -> None:
    """Journal search must send the DOI row-template override.

    Without it the search endpoint replies with wizard journal rows whose
    clear_journal_error HTMX targets #journal-error, which does not exist in
    the DOI type-change modal.
    """
    response = submit_for_preview(client, scenario.doi.value())
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "article")

    content = form_response.content.decode()
    assert "fundingrequests/partials/doi_journal_row.html" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_load_monograph_form_publisher_search_requests_stripped_row_template(
    client: Client, scenario: ArticleScenario
) -> None:
    """Publisher search must send the DOI row-template override.

    Without it the search endpoint replies with wizard publisher rows whose
    clear_publisher_error HTMX targets #publisher-error, which does not exist
    in the DOI type-change modal.
    """
    response = submit_for_preview(client, scenario.doi.value())
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "monograph")

    content = form_response.content.decode()
    assert "fundingrequests/partials/doi_publisher_row.html" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_load_monograph_form_shows_prefilled_publisher(
    client: Client, scenario: ArticleScenario
) -> None:
    """HTMX endpoint for monograph form should pre-fill publisher from original metadata."""
    response = submit_for_preview(client, scenario.doi.value())
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "monograph")

    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "publisher_name" in content
    assert "Test Publisher" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_preview_page_shows_type_selector_with_htmx(
    client: Client, scenario: ArticleScenario
) -> None:
    """Preview page should show a publication type selector to change the type.

    The selector provides both type options and the current type's fix form
    is pre-rendered so the user can immediately supply missing data.
    """
    response = submit_for_preview(client, scenario.doi.value())
    preview_url = response["Location"]
    preview_response = client.get(preview_url)

    assert preview_response.status_code == 200
    content = preview_response.content.decode()

    # Entry point to change publication type
    assert "Change Publication Type" in content
    # Both type options are available
    assert "Monograph" in content
    # The current type's fix form is pre-rendered (hidden publication_type input)
    assert 'name="publication_type"' in content


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
@pytest.mark.usefixtures("logged_in")
def test_submit_type_change_monograph_without_publisher_shows_inline_error(
    client: Client, scenario: ArticleScenario
) -> None:
    """Submitting monograph form without selecting a publisher returns partial with error."""
    response = submit_for_preview(client, scenario.doi.value())
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
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """Submitting article form without selecting a journal returns partial with error."""
    doi_str = "10.1234/book.no-journal"
    BookScenario(fake_doi_client, doi_str).with_title("Test Book").with_isbn(
        "978-3-16-148410-0"
    ).setup_client()

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    change_response = submit_type_change(client, session_key, "article", journal_title="Nature")

    assert change_response.status_code == 200
    assert "HX-Redirect" not in change_response
    content = change_response.content.decode()
    assert "Please select a journal before applying." in content
    assert 'value="Nature"' in content
    session_data = client.session[session_key]
    assert "journal_id" not in session_data


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_reset_type_clears_override_and_restores_original_type(
    client: Client, scenario: ArticleScenario
) -> None:
    """Reset endpoint clears override and restores the auto-detected publication type."""
    response = submit_for_preview(client, scenario.doi.value())
    session_key = get_session_key(response)
    publisher = modelfactory.publisher(name="Test Publisher")
    submit_type_change(client, session_key, "monograph", publisher=publisher.pk)

    # Reset to original
    _ = reset_type(client, session_key)

    saved = save_doi_import(client, session_key)
    location = saved["Location"]
    request_id = int(location.removesuffix("/").split("/")[-1])

    actual = repository.get_by_id(FundingRequestId(request_id))
    assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_override_article_to_monograph_and_save(
    client: Client,
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """Full workflow: article DOI → override to monograph → save creates Monograph."""

    publisher = modelfactory.publisher(name="Springer")
    scenario = (
        ArticleScenario(fake_doi_client)
        .with_title("Test Article")
        .with_publisher("Springer")
        .with_online_date(datetime.date(2024, 1, 1))
        .setup_client()
    )

    response = submit_for_preview(client, scenario.doi.value())
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
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """Full workflow: monograph DOI → override to article → save creates Publication."""
    doi_str = "10.1234/book.override"

    journal_pk = int(
        journal_services.create(
            title=NonEmptyStr("Nature"),
            eissn=Issn("1476-4687"),
            publisher_id=PublisherId(modelfactory.publisher(name="Test Publisher").pk),
        )
    )
    BookScenario(fake_doi_client, doi_str).with_title("Test Book").with_publisher(
        "Test Publisher"
    ).with_isbn("978-3-16-148410-0").setup_client()

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    submit_type_change(client, session_key, "article", journal=journal_pk)
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
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """DOI metadata fetch failure displays error message without redirect."""
    ArticleScenario(fake_doi_client, "10.1234/broken.doi").with_error().setup_client()

    response = submit_for_preview(client, "10.1234/broken.doi")

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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__save_preview__article_with_print_issn_only__redirects_back_with_error(
    client: Client,
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """Saving a preview with a print-ISSN-only journal shows an error and redirects back.

    When a journal article has a journal with only a print ISSN (no E-ISSN),
    DOIPreviewSaveView must catch InvalidMetadataError and surface it as a Django
    messages error — redirecting back to the preview page — instead of raising a 500.
    """
    doi_str = "10.1234/print-issn-only"
    ArticleScenario(fake_doi_client, doi_str).with_title("Print-ISSN-Only Article").with_journal(
        title="Print-Only Journal", eissn=None, issn="1234-5678"
    ).without_online_date().setup_client()

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    save_response = save_doi_import(client, session_key)

    # Must redirect back to the preview page (not crash with 500)
    assertRedirects(
        save_response,
        reverse("fundingrequests:doi_preview_detail", kwargs={"session_key": session_key}),
    )
    # Must surface an error message to the user (read from the redirect response's request)
    msgs = list(get_messages(cast(Any, save_response).wsgi_request))
    assert any("E-ISSN" in str(m) for m in msgs)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__preview_page__article_with_print_issn_only__does_not_display_print_issn(
    client: Client,
    fake_doi_client: InMemoryDOIMetadataClient,
) -> None:
    """Preview page must not display the print ISSN when a journal has no E-ISSN.

    Coda only supports online journals (E-ISSN required). When a journal article
    has only a print ISSN, the preview page should not show that ISSN at all —
    the E-ISSN missing warning already informs the user. Displaying the print ISSN
    would be misleading since it cannot be used to identify the journal in coda.
    """
    doi_str = "10.1234/print-issn-only.preview"
    ArticleScenario(fake_doi_client, doi_str).with_title("Print-ISSN-Only Article").with_journal(
        title="Print-Only Journal", eissn=None, issn="1234-5678"
    ).setup_client()

    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    preview_response = client.get(preview_url)

    assert preview_response.status_code == 200
    assert b"1234-5678" not in preview_response.content

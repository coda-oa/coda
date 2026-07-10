"""Tests for Mass DOI Import Preview workflow.

User journey:
1. User enters multiple DOIs on textarea input form
2. System fetches all metadata and shows a summary list
3. User can click "View details" to access existing single-DOI preview (override only)
4. User clicks "Import All" → System persists all to database
5. User sees import result summary
"""

from collections.abc import Generator
from typing import cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
)
from coda.apps.journals import services as journal_services
from coda.contexts.fundingrequest.services.doi_import.doi_client import (
    InMemoryDOIMetadataClient,
    crossref,
)
from coda.domain.contract import PublisherId
from coda.domain.issn import Issn
from coda.domain.string import NonEmptyStr
from tests import modelfactory
from tests.contexts.fundingrequest.fixtures.sample_metadata import (
    ArticleScenario,
    BookScenario,
)
from tests.fundingrequests.test_doi_import_preview import submit_type_change


@pytest.fixture
def fake_doi_client() -> InMemoryDOIMetadataClient:
    return InMemoryDOIMetadataClient()


@pytest.fixture(autouse=True)
def inject_fake_doi_client(fake_doi_client: InMemoryDOIMetadataClient) -> Generator[None]:
    """Inject fake DOI client into mass import views via dependency injection."""
    from coda.apps.fundingrequests.views.mass_doi_import import (
        MassDOIImportInputView,
        MassDOIPreviewSaveView,
        MassDOIPreviewView,
    )

    MassDOIImportInputView.doi_client = fake_doi_client
    MassDOIPreviewView.doi_client = fake_doi_client
    MassDOIPreviewSaveView.doi_client = fake_doi_client
    # Also inject into existing views for cross-context tests
    DOIImportInputView.doi_client = fake_doi_client
    DOIPreviewDetailView.doi_client = fake_doi_client
    DOIPreviewSaveView.doi_client = fake_doi_client

    yield

    MassDOIImportInputView.doi_client = crossref
    MassDOIPreviewView.doi_client = crossref
    MassDOIPreviewSaveView.doi_client = crossref
    DOIImportInputView.doi_client = crossref
    DOIPreviewDetailView.doi_client = crossref
    DOIPreviewSaveView.doi_client = crossref


def submit_many_for_preview(client: Client, dois_text: str) -> HttpResponse:
    return cast(
        HttpResponse,
        client.post(
            reverse("fundingrequests:mass_doi_import_input"),
            data={"dois": dois_text},
        ),
    )


def get_mass_preview(client: Client, session_key: str) -> HttpResponse:
    return cast(
        HttpResponse,
        client.get(
            reverse("fundingrequests:mass_doi_preview", kwargs={"session_key": session_key})
        ),
    )


def save_mass_doi_import(client: Client, session_key: str) -> HttpResponse:
    return cast(
        HttpResponse,
        client.post(
            reverse("fundingrequests:mass_doi_preview_save", kwargs={"session_key": session_key})
        ),
    )


def view_mass_import_result(client: Client, result_key: str) -> HttpResponse:
    return cast(
        HttpResponse,
        client.get(reverse("fundingrequests:mass_doi_result", kwargs={"result_key": result_key})),
    )


class TestMassDOIImportInputView:
    """Tests for the mass DOI input page."""

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_import_input__get__returns_200(self, client: Client) -> None:
        response = client.get(reverse("fundingrequests:mass_doi_import_input"))
        assert response.status_code == 200

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_import_input__post_two_valid_dois__redirects_to_preview(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        ArticleScenario(client=fake_doi_client, doi="10.1234/mass.view.a").setup_client()
        BookScenario(client=fake_doi_client, doi="10.1234/mass.view.b").setup_client()

        response = submit_many_for_preview(client, "10.1234/mass.view.a\n10.1234/mass.view.b")

        assertRedirects(
            response,
            reverse(
                "fundingrequests:mass_doi_preview",
                kwargs={"session_key": get_session_key(response)},
            ),
        )

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_import_input__post_mixed_valid_and_invalid__shows_warning(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        ArticleScenario(client=fake_doi_client, doi="10.1234/mass.mixed").setup_client()

        response = submit_many_for_preview(client, "10.1234/mass.mixed\nnot-a-doi\nalso-invalid")

        # Should still redirect to preview (valid DOIs processed)
        assertRedirects(
            response,
            reverse(
                "fundingrequests:mass_doi_preview",
                kwargs={"session_key": get_session_key(response)},
            ),
            fetch_redirect_response=False,
        )

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_import_input__post_all_invalid__re_renders_with_error(
        self,
        client: Client,
    ) -> None:
        response = submit_many_for_preview(client, "not-a-doi")

        assert response.status_code == 200
        content = response.content.decode()
        assert "No valid DOIs" in content
        assert "doi-import/mass/" in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_import_input__post_empty__re_renders_with_error(
        self,
        client: Client,
    ) -> None:
        response = submit_many_for_preview(client, "")

        assert response.status_code == 200
        content = response.content.decode().lower()
        assert "enter at least one doi" in content or "no valid dois" in content


class TestMassDOIPreviewView:
    """Tests for the mass DOI preview list page."""

    def _create_preview_session(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
        dois: list[str],
    ) -> str:
        """Create a mass import session and return its session key."""
        for doi_str in dois:
            ArticleScenario(client=fake_doi_client, doi=doi_str).setup_client()

        response = submit_many_for_preview(client, "\n".join(dois))
        return get_session_key(response)

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__displays_results_table(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        session_key = self._create_preview_session(
            client, fake_doi_client, ["10.1234/mass.preview.a"]
        )

        response = get_mass_preview(client, session_key)

        assert response.status_code == 200
        content = response.content.decode()
        assert "10.1234/mass.preview.a" in content
        assert "View details" in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__article_without_journal__shows_warning(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Article missing journal metadata → warning is displayed in mass preview table."""
        doi_str = "10.1234/mass.no-journal"
        ArticleScenario(client=fake_doi_client, doi=doi_str).with_title(
            "Article Without Journal"
        ).without_journal().without_online_date().setup_client()

        response = submit_many_for_preview(client, doi_str)
        session_key = get_session_key(response)
        preview_response = get_mass_preview(client, session_key)

        assert preview_response.status_code == 200
        content = preview_response.content.decode()
        assert "Journal metadata is missing" in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__monograph_without_publisher__shows_warning(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Monograph missing publisher metadata → warning is displayed in mass preview table."""
        doi_str = "10.1234/mass.no-publisher"
        BookScenario(client=fake_doi_client, doi=doi_str).with_title(
            "Book Without Publisher"
        ).without_publisher().without_print_date().setup_client()

        response = submit_many_for_preview(client, doi_str)
        session_key = get_session_key(response)
        preview_response = get_mass_preview(client, session_key)

        assert preview_response.status_code == 200
        content = preview_response.content.decode()
        assert "Publisher metadata is missing" in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__complete_metadata__no_warnings(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Complete metadata → no warning indicators in mass preview."""
        doi_str = "10.1234/mass.complete"
        ArticleScenario(client=fake_doi_client, doi=doi_str).with_title(
            "Complete Article"
        ).setup_client()

        response = submit_many_for_preview(client, doi_str)
        session_key = get_session_key(response)
        preview_response = get_mass_preview(client, session_key)

        assert preview_response.status_code == 200
        content = preview_response.content.decode()
        assert "Journal metadata is missing" not in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__session_expired__returns_404(
        self,
        client: Client,
    ) -> None:
        response = get_mass_preview(client, "invalid_session_key")
        assert response.status_code == 404

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__after_type_override__shows_overridden_type(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Given a mass import with an article, when the type is overridden to monograph
        via the detail page, the preview table should show the overridden type."""
        publisher = modelfactory.publisher(name="Test Publisher")
        ArticleScenario(client=fake_doi_client, doi="10.1234/mass.override").with_publisher(
            "Test Publisher"
        ).setup_client()

        session_key = self._create_preview_session(
            client, fake_doi_client, ["10.1234/mass.override"]
        )

        mass_session = client.session[session_key]
        child_key = mass_session["results"][0]["child_key"]

        # Override type to monograph via the public HTTP endpoint
        submit_type_change(client, child_key, "monograph", publisher=publisher.pk)

        response = get_mass_preview(client, session_key)

        assert response.status_code == 200
        content = response.content.decode()
        assert "monograph" in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__after_type_override__clears_stale_warnings(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Given a mass import with an article missing journal metadata (showing a warning),
        when the type is overridden to monograph, the stale journal warning should be cleared."""
        publisher = modelfactory.publisher(name="Test Publisher")

        # Set up the scenario manually (cannot use _create_preview_session
        # which creates a new default scenario overwriting our custom setup)
        doi_str = "10.1234/mass.warning"
        ArticleScenario(client=fake_doi_client, doi=doi_str).with_title(
            "Article With Warning"
        ).without_journal().with_publisher("Test Publisher").setup_client()

        response = submit_many_for_preview(client, doi_str)
        session_key = get_session_key(response)

        mass_session = client.session[session_key]
        child_key = mass_session["results"][0]["child_key"]

        # Override type to monograph via the public HTTP endpoint
        submit_type_change(client, child_key, "monograph", publisher=publisher.pk)

        response = get_mass_preview(client, session_key)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Journal metadata is missing" not in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview__after_article_with_journal_override__clears_stale_warnings(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Given a mass import with an article missing journal metadata (showing a warning),
        when the type is overridden to article with a specific journal, the stale
        journal warning should be cleared."""
        publisher = modelfactory.publisher(name="Test Publisher")
        journal_pk = int(
            journal_services.create(
                title=NonEmptyStr("Test Journal"),
                eissn=Issn("1234-1231"),
                publisher_id=PublisherId(publisher.pk),
            )
        )

        doi_str = "10.1234/mass.journal.override"
        ArticleScenario(client=fake_doi_client, doi=doi_str).with_title(
            "Article Needing Journal"
        ).without_journal().with_publisher("Test Publisher").setup_client()

        response = submit_many_for_preview(client, doi_str)
        session_key = get_session_key(response)

        mass_session = client.session[session_key]
        child_key = mass_session["results"][0]["child_key"]

        # Override to article with a journal via the public HTTP endpoint
        submit_type_change(client, child_key, "article", journal=journal_pk)

        response = get_mass_preview(client, session_key)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Journal metadata is missing" not in content


class TestMassDOIPreviewSaveView:
    """Tests for saving mass DOI imports."""

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__mass_doi_preview_save__single_doi__creates_funding_request(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        scenario = (
            ArticleScenario(client=fake_doi_client, doi="10.1234/mass.save")
            .setup_db()
            .setup_client()
        )

        # Create preview session
        response = submit_many_for_preview(client, scenario.doi.value())
        session_key = get_session_key(response)

        # Save — should redirect to result page
        response = save_mass_doi_import(client, session_key)
        assert response.status_code == 302
        result_key = response["Location"].split("/")[-2]

        # Follow redirect to verify result content
        response = view_mass_import_result(client, result_key)

        assert response.status_code == 200
        content = response.content.decode()
        assert "1" in content or "imported" in content.lower()

        # Verify original session is cleaned up
        assert session_key not in client.session


class TestDOIPreviewInMassContext:
    """Tests for the existing single-DOI preview when accessed from mass import."""

    def _create_mass_session_and_get_child_key(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> tuple[str, str]:
        """Create mass import with one DOI and return (mass_key, child_key)."""
        ArticleScenario(client=fake_doi_client, doi="10.1234/mass.context").setup_client()
        response = submit_many_for_preview(client, "10.1234/mass.context")
        mass_key = get_session_key(response)
        mass_session = client.session[mass_key]
        return mass_key, mass_session["results"][0]["child_key"]

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__doi_preview_detail__in_mass_context__shows_back_link(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        mass_key, child_key = self._create_mass_session_and_get_child_key(client, fake_doi_client)

        response = client.get(
            reverse("fundingrequests:doi_preview_detail", kwargs={"session_key": child_key}),
            {"mass_session": mass_key},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Back to mass import" in content
        assert "Save to Database" not in content

    @pytest.mark.django_db
    @pytest.mark.usefixtures("logged_in")
    def test__doi_single_preview_save__in_mass_context__does_not_save(
        self,
        client: Client,
        fake_doi_client: InMemoryDOIMetadataClient,
    ) -> None:
        """Given a mass import context, single-DOI save redirects to mass preview."""
        mass_key, child_key = self._create_mass_session_and_get_child_key(client, fake_doi_client)

        response = client.post(
            f"{reverse('fundingrequests:doi_preview_save', kwargs={'session_key': child_key})}?mass_session={mass_key}",
        )

        assertRedirects(
            response,
            reverse("fundingrequests:mass_doi_preview", kwargs={"session_key": mass_key}),
        )
        assert fundingrequest_repository.first() is None


def get_session_key(response: HttpResponse) -> str:
    return response["Location"].split("/")[-2]

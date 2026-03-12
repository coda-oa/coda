"""DOI Import Preview Views.

Handles the preview workflow for DOI imports:
1. DOI input → fetch metadata → create session
2. Preview detail page (session-based, not persisted, read-only)
3. Final save (persist to database, then edit using regular wizards)
"""

from typing import Any, ClassVar
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.views import View
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests.queries.preview_context_builder import build_preview_context
from coda.apps.journals import services as journal_services
from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services._crossref_type_detector import detect_publication_type
from coda.contexts.publication.services.doi_client import (
    CrossrefDoiClient,
    DOIMetadataClient,
    DOINotFoundError,
    DOIFetchError,
)
from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideImportAsArticle,
    OverrideImportAsMonograph,
    OverrideImportPublicationType,
)
from coda.contexts.publication.services.errors import DOIAlreadyImported, InvalidMetadataError
from coda.domain.contract import PublisherId
from coda.domain.publication import JournalId
from coda.domain.publication.links import Doi


def _build_override_from_session(
    session_data: dict[str, Any],
) -> OverrideImportPublicationType | None:
    """Reconstruct override object from session data using match statement."""
    match session_data.get("publication_type"):
        case "article" if journal_id := session_data.get("journal_id"):
            return OverrideImportAsArticle(journal_id=JournalId(journal_id))
        case "monograph" if publisher_id := session_data.get("publisher_id"):
            return OverrideImportAsMonograph(publisher_id=PublisherId(publisher_id))
        case _:
            return None


class DOIImportInputView(LoginRequiredMixin, View):
    """Handle DOI input form submission and create preview session.

    Class attribute `doi_client` can be overridden for testing via subclassing.
    """

    doi_client: ClassVar[DOIMetadataClient] = CrossrefDoiClient()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Display DOI input form."""
        return render(request, "fundingrequests/doi_import_input.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        Process DOI input, fetch raw metadata, create session, redirect to preview.

        Workflow:
        1. Get DOI from POST data
        2. Fetch raw metadata from Crossref (not a preview DTO)
        3. Detect publication type
        4. Store doi, original_metadata, publication_type in session
        5. Redirect to preview detail page
        """
        doi_str = request.POST.get("doi", "")

        try:
            doi = Doi(doi_str)
            metadata = self.doi_client.fetch(doi)
            detected_type = detect_publication_type(metadata)

            session_key = f"doi_preview_{uuid4()}"
            request.session[session_key] = {
                "doi": str(doi),
                "original_metadata": metadata.model_dump(mode="json"),
                "publication_type": detected_type,
            }

            return redirect("fundingrequests:doi_preview_detail", session_key=session_key)

        except (DOINotFoundError, DOIFetchError) as e:
            context = {"error": f"Failed to import DOI: {str(e)}"}
            return render(request, "fundingrequests/doi_import_input.html", context)
        except Exception:
            context = {"error": "An unexpected error occurred. Please try again."}
            return render(request, "fundingrequests/doi_import_input.html", context)


class DOIPreviewDetailView(LoginRequiredMixin, View):
    """Display read-only preview detail page loading data from session (not database).

    Users can review imported data before saving. After saving to database,
    they can edit using the regular funding request update wizards.
    """

    doi_client: ClassVar[DOIMetadataClient] = CrossrefDoiClient()

    def get(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Load preview data from session, build preview on demand, display detail page.

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Rendered preview detail page (read-only, no edit buttons)
        """
        session_data = request.session.get(session_key)

        if not session_data:
            return HttpResponse("Preview session not found or expired", status=404)

        doi = Doi(session_data["doi"])
        metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
        doi_service = DOIImportService(doi_client=self.doi_client, metadata_cache={doi: metadata})
        override = _build_override_from_session(session_data)

        if override:
            preview_dto = doi_service.build_preview_with_type_override(doi, override)
        else:
            preview_dto = doi_service.fetch_doi_preview(doi)

        context = build_preview_context(preview_dto, session_key)
        return render(request, "fundingrequests/doi_preview_detail.html", context)


class DOIPreviewSaveView(LoginRequiredMixin, View):
    """Persist preview session data to database and redirect to real detail page.

    Class attribute `doi_client` can be overridden for testing via subclassing.
    """

    doi_client: ClassVar[DOIMetadataClient] = CrossrefDoiClient()

    def post(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Save preview data from session to database.

        Workflow:
        1. Load session data
        2. Reconstruct metadata + override from session
        3. Use DOIImportService with pre-populated metadata_cache (avoids re-fetching)
        4. Clean up session
        5. Redirect to real detail page

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Redirect to funding request detail page
        """
        session_data = request.session.get(session_key)

        if not session_data:
            return HttpResponse("Preview session not found or expired", status=404)

        doi = Doi(session_data["doi"])
        metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
        doi_service = DOIImportService(doi_client=self.doi_client, metadata_cache={doi: metadata})
        override = _build_override_from_session(session_data)

        try:
            fr_id = doi_service.import_from_doi(doi, override)
        except DOIAlreadyImported as e:
            messages.error(request, self._format_error(e))
            return redirect("fundingrequests:doi_preview_detail", session_key=session_key)
        except InvalidMetadataError as e:
            messages.error(request, str(e))
            return redirect("fundingrequests:doi_preview_detail", session_key=session_key)

        del request.session[session_key]
        return redirect("fundingrequests:detail", pk=fr_id)

    def _format_error(self, e: DOIAlreadyImported) -> SafeString:
        author_names = ", ".join(a.name for a in e.publication_authors)
        return format_html(
            "<p>DOI {} already exists in database</p>"
            "<p><strong>Title:</strong> {}</p>"
            "<p><strong>Authors:</strong> {}</p>",
            e.doi,
            e.publication_title,
            author_names,
        )


@login_required
def doi_preview_load_type_form(request: HttpRequest, session_key: str) -> HttpResponse:
    """HTMX endpoint: Load form partial for switching publication type.

    Uses original_metadata for smart pre-filling in both directions:
    - article form: pre-fill journal search from original_metadata["journal"]["title"]
    - monograph form: pre-fill publisher search from original_metadata["publisher"]
    """
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)

    requested_type = request.GET.get("publication_type", "article")
    original_metadata = session_data.get("original_metadata", {})

    if requested_type == "article":
        journal_data = original_metadata.get("journal") or {}
        # Use the metadata title as fallback so the initial load auto-searches.
        metadata_title = journal_data.get("title", "")
        journal_title_search = request.GET.get("journal_title", "") or metadata_title
        journals = (
            list(journal_services.find_by_title(journal_title_search))
            if journal_title_search
            else []
        )
        context = {
            "session_key": session_key,
            "journal_title": journal_title_search,
            "journals": journals,
        }
        return render(
            request,
            "fundingrequests/partials/doi_type_change_to_article.html",
            context,
        )
    else:
        context = {
            "session_key": session_key,
            "suggested_publisher": original_metadata.get("publisher", ""),
            "publishers": [],
        }
        return render(
            request,
            "fundingrequests/partials/doi_type_change_to_monograph.html",
            context,
        )


@login_required
@require_POST
def doi_preview_apply_type_change(request: HttpRequest, session_key: str) -> HttpResponse:
    """Handle type change form submission — stores selected entity ID in session.

    Does not build or store a preview — the detail view rebuilds on demand.

    On validation failure: re-renders the appropriate partial with an inline error
    message so HTMX can swap it back into #type-change-form.
    On success: returns HX-Redirect header so HTMX triggers a full page navigation
    to the preview detail page.
    """
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)

    requested_type = request.POST.get("publication_type")
    if requested_type not in ("article", "monograph"):
        return HttpResponse("Invalid publication type", status=400)

    original_metadata = session_data.get("original_metadata", {})

    match requested_type:
        case "article":
            journal_id_str = request.POST.get("journal")
            if not journal_id_str:
                journal_data = original_metadata.get("journal") or {}
                context = {
                    "session_key": session_key,
                    "journal_title": request.POST.get(
                        "journal_title", journal_data.get("title", "")
                    ),
                    "journals": [],
                    "error": "Please select a journal before applying.",
                }
                return render(
                    request,
                    "fundingrequests/partials/doi_type_change_to_article.html",
                    context,
                )
            session_data["publication_type"] = "article"
            session_data["journal_id"] = int(journal_id_str)
            session_data.pop("publisher_id", None)
        case "monograph":
            publisher_id_str = request.POST.get("publisher")
            if not publisher_id_str:
                context = {
                    "session_key": session_key,
                    "suggested_publisher": request.POST.get(
                        "publisher_name", original_metadata.get("publisher", "")
                    ),
                    "publishers": [],
                    "error": "Please select a publisher before applying.",
                }
                return render(
                    request,
                    "fundingrequests/partials/doi_type_change_to_monograph.html",
                    context,
                )
            session_data["publication_type"] = "monograph"
            session_data["publisher_id"] = int(publisher_id_str)
            session_data.pop("journal_id", None)
        case _:
            return HttpResponse("Invalid publication type", status=400)

    request.session[session_key] = session_data
    request.session.modified = True
    response = HttpResponse()
    response["HX-Redirect"] = reverse(
        "fundingrequests:doi_preview_detail", kwargs={"session_key": session_key}
    )
    return response


@login_required
@require_POST
def doi_preview_reset_type(request: HttpRequest, session_key: str) -> HttpResponse:
    """HTMX endpoint: Reset publication type override to original auto-detected type.

    Clears any journal_id/publisher_id override from session, re-derives the
    original type from original_metadata, and issues HX-Redirect to the preview page.
    """
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)

    metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
    original_type = detect_publication_type(metadata)

    session_data["publication_type"] = original_type
    session_data.pop("journal_id", None)
    session_data.pop("publisher_id", None)

    request.session[session_key] = session_data
    request.session.modified = True
    response = HttpResponse()
    response["HX-Redirect"] = reverse(
        "fundingrequests:doi_preview_detail", kwargs={"session_key": session_key}
    )
    return response

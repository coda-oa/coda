"""DOI Import Preview Views.

Handles the preview workflow for DOI imports:
1. DOI input → fetch metadata → create session
2. Preview detail page (session-based, not persisted, read-only)
3. Final save (persist to database, then edit using regular wizards)
"""

from typing import ClassVar
from uuid import uuid4

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.views import View

from coda.apps.fundingrequests.queries.preview_context_builder import build_preview_context
from coda.contexts.publication.dto.preview import PreviewFundingRequest
from coda.contexts.publication.services.doi_client import CrossrefDoiClient, DOIMetadataClient
from coda.contexts.publication.services.doi_import_service import (
    DOIAlreadyImported,
    DOIImportService,
)
from coda.domain.publication.links import Doi


class DOIImportInputView(View):
    """Handle DOI input form submission and create preview session.

    Class attribute `doi_client` can be overridden for testing via subclassing.
    """

    doi_client: ClassVar[DOIMetadataClient] = CrossrefDoiClient()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Display DOI input form."""
        return render(request, "fundingrequests/doi_import_input.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        Process DOI input, fetch metadata, create session, redirect to preview.

        Workflow:
        1. Get DOI from POST data
        2. Use DOIImportService to fetch metadata and build DTO
        3. Store DTO in session using model_dump(mode="json") for JSON serialization
        4. Generate unique session key
        5. Redirect to preview detail page
        """
        doi_str = request.POST.get("doi", "")

        try:
            doi = Doi(doi_str)

            # Fetch metadata and build DTO (doesn't persist to database)
            doi_service = DOIImportService(doi_client=self.doi_client)
            creation_dto = doi_service.fetch_doi_preview(doi)

            # Store in session using model_dump(mode="json") for JSON serialization
            # Pydantic automatically handles polymorphic types via discriminated union
            session_key = f"doi_preview_{uuid4()}"
            session_dto = creation_dto.model_dump(mode="json")
            session_dto["doi"] = str(doi)
            request.session[session_key] = session_dto

            # Redirect to preview detail page
            return redirect("fundingrequests:doi_preview_detail", session_key=session_key)

        except Exception as e:
            # Handle errors and re-display form with error message
            context = {
                "error": f"Failed to import DOI: {str(e)}",
            }
            return render(request, "fundingrequests/doi_import_input.html", context)


class DOIPreviewDetailView(View):
    """Display read-only preview detail page loading data from session (not database).

    Users can review imported data before saving. After saving to database,
    they can edit using the regular funding request update wizards.
    """

    def get(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Load preview data from session and display detail page.

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Rendered preview detail page (read-only, no edit buttons)
        """

        # Load preview data from session
        preview_data = request.session.get(session_key)

        if not preview_data:
            # Handle missing session data (expired or invalid key)
            return HttpResponse("Preview session not found or expired", status=404)

        # Build context from DTOs (no edit URLs - preview is read-only)
        context = build_preview_context(preview_data, session_key)

        return render(request, "fundingrequests/doi_preview_detail.html", context)


class DOIPreviewSaveView(View):
    """Persist preview session data to database and redirect to real detail page.

    Class attribute `doi_client` can be overridden for testing via subclassing.
    """

    doi_client: ClassVar[DOIMetadataClient] = CrossrefDoiClient()

    def post(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Save preview data from session to database.

        Workflow:
        1. Load preview data from session
        2. Reconstruct DTO from session and create cache
        3. Use DOIImportService with cache (avoids re-fetching from Crossref)
        4. Clean up session
        5. Redirect to real detail page

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Redirect to funding request detail page
        """
        preview_data = request.session.get(session_key)

        if not preview_data:
            return HttpResponse("Preview session not found or expired", status=404)

        doi = Doi(preview_data.pop("doi"))
        preview_dto = PreviewFundingRequest.model_validate(preview_data)

        cache = {doi: preview_dto}
        doi_service = DOIImportService(doi_client=self.doi_client, cache=cache)

        try:
            fr_id = doi_service.import_from_doi(doi)
        except DOIAlreadyImported as e:
            messages.error(request, self._format_error(e))
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

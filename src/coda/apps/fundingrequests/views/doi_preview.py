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
from django.views.decorators.http import require_GET, require_POST

from coda import formdata
from coda.apps.dto import CodaBaseDto
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.queries.preview_context_builder import (
    build_preview_context,
    tag_existing_funders,
)
from coda.apps.fundingrequests.views.decorators import require_session
from coda.apps.fundingrequests.views.mixins import MassImportAwareMixin
from coda.contexts.fundingrequest.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.fundingrequest.services.doi_import._service import (
    DOIImportService,
    OverrideFunding,
    OverrideImport,
    OverrideImportTypeAdapter,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client import DOIMetadataClient, crossref
from coda.contexts.fundingrequest.services.doi_import.doi_client import errors as doi_errors
from coda.contexts.fundingrequest.services.doi_import.doi_client.publication_type_detector import (
    detect_publication_type,
)
from coda.contexts.fundingrequest.services.doi_import.errors import (
    DOIAlreadyImported,
    InvalidMetadataError,
)
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.publication import JournalId
from coda.domain.publication.links import Doi


def _load_override(session_data: dict[str, Any]) -> OverrideImport:
    override = OverrideImportTypeAdapter.validate_python(session_data["override"])
    return override


def _dump_override(session_data: dict[str, Any], override: OverrideImport) -> None:
    session_data["override"] = OverrideImportTypeAdapter.dump_python(override, mode="json")


class DOIImportInputView(LoginRequiredMixin, View):
    """Handle DOI input form submission and create preview session.

    Class attribute `doi_client` can be overridden for testing via subclassing.
    """

    doi_client: ClassVar[DOIMetadataClient] = crossref

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
            metadata = self.doi_client.fetch_publication(doi)
            detected_type = detect_publication_type(metadata)

            session_key = f"doi_preview_{uuid4()}"
            request.session[session_key] = {
                "doi": str(doi),
                "original_metadata": metadata.model_dump(mode="json"),
                "publication_type": detected_type,
            }
            _dump_override(request.session[session_key], OverrideImport.empty())

            return redirect("fundingrequests:doi_preview_detail", session_key=session_key)

        except (doi_errors.DOINotFoundError, doi_errors.DOIFetchError) as e:
            context = {"error": f"Failed to import DOI: {str(e)}"}
            return render(request, "fundingrequests/doi_import_input.html", context)
        except Exception:
            context = {"error": "An unexpected error occurred. Please try again."}
            return render(request, "fundingrequests/doi_import_input.html", context)


class DOIPreviewDetailView(LoginRequiredMixin, MassImportAwareMixin, View):
    """Display read-only preview detail page loading data from session (not database).

    Users can review imported data before saving. After saving to database,
    they can edit using the regular funding request update wizards.

    When accessed from a mass import context (detected via
    ``mass_import_session_key`` in child session data), the save button is
    hidden and a "Back to mass import" link is shown instead.
    """

    doi_client: ClassVar[DOIMetadataClient] = crossref

    @require_session()
    def get(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Load preview data from session, build preview on demand, display detail page.

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Rendered preview detail page (read-only, no edit buttons)
        """
        session_data = request.session[session_key]

        doi = Doi(session_data["doi"])
        metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
        doi_service = DOIImportService(doi_client=self.doi_client, metadata_cache={doi: metadata})
        override = _load_override(session_data)

        if override:
            preview_dto = doi_service.preview_with_override(doi, override)
        else:
            preview_dto = doi_service.fetch_doi_preview(doi)

        context = build_preview_context(preview_dto, session_key)
        context.update(self.get_mass_import_context(session_data))

        return render(request, "fundingrequests/doi_preview_detail.html", context)


class DOIPreviewSaveView(LoginRequiredMixin, MassImportAwareMixin, View):
    """Persist preview session data to database and redirect to real detail page.

    When accessed from a mass import context (detected via
    ``mass_import_session_key`` in child session data), redirects back to
    the mass preview instead of saving the single DOI.

    Class attribute ``doi_client`` can be overridden for testing via subclassing.
    """

    doi_client: ClassVar[DOIMetadataClient] = crossref

    @require_session()
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
        session_data = request.session[session_key]

        response = self.redirect_if_mass_import(session_data)
        if response:
            return response

        doi = Doi(session_data["doi"])
        metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
        doi_service = DOIImportService(doi_client=self.doi_client, metadata_cache={doi: metadata})
        override = _load_override(session_data)

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


def _render_article_type_form(
    request: HttpRequest,
    *,
    error: str = "",
) -> HttpResponse:
    """Render the article type-change form partial. Journal search is handled by wizard_find_journal."""
    context: dict[str, Any] = {
        "journals": [],
        "suggested_journal": request.POST.get("journal_title", ""),
    }
    if error:
        context["error"] = error
    return render(request, "fundingrequests/partials/doi_type_change_to_article.html", context)


def _render_monograph_type_form(
    request: HttpRequest,
    original_metadata: dict[str, Any],
    *,
    error: str = "",
) -> HttpResponse:
    """Render the monograph type-change form partial, pre-filling from original metadata."""
    suggested_publisher = request.POST.get("publisher_name", original_metadata.get("publisher", ""))
    context: dict[str, Any] = {
        "suggested_publisher": suggested_publisher,
    }
    if error:
        context["error"] = error
    return render(request, "fundingrequests/partials/doi_type_change_to_monograph.html", context)


@require_session()
@login_required
@require_GET
def doi_preview_load_type_form(request: HttpRequest, session_key: str) -> HttpResponse:
    """HTMX endpoint: Return the tab bar + form for the requested publication type.

    Renders the full swappable tab-content fragment so the active tab marker
    and the form content are always in sync.
    Uses original_metadata for smart pre-filling (e.g. suggested_publisher).
    """
    session_data = request.session[session_key]

    requested_type = request.GET.get("publication_type", "article")
    original_metadata = session_data.get("original_metadata", {})

    context: dict[str, Any] = {
        "session_key": session_key,
        "current_publication_type": requested_type,
        "suggested_publisher": original_metadata.get("publisher", ""),
        "journals": [],
        "publishers": [],
    }

    return render(request, "fundingrequests/partials/doi_type_change_tab_content.html", context)


@require_session()
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
    session_data = request.session[session_key]

    requested_type = request.POST.get("publication_type")
    if requested_type not in ("article", "monograph"):
        return HttpResponse("Invalid publication type", status=400)

    original_metadata = session_data.get("original_metadata", {})

    override = _load_override(session_data)
    match requested_type:
        case "article":
            journal_id_str = request.POST.get("journal")
            if not journal_id_str:
                return _render_article_type_form(
                    request,
                    error="Please select a journal before applying.",
                )

            override = override.into_article(JournalId(int(journal_id_str)))
            _dump_override(session_data, override)
        case "monograph":
            publisher_id_str = request.POST.get("publisher")
            if not publisher_id_str:
                return _render_monograph_type_form(
                    request,
                    original_metadata,
                    error="Please select a publisher before applying.",
                )
            override = override.into_monograph(PublisherId(int(publisher_id_str)))
            _dump_override(session_data, override)

    request.session[session_key] = session_data
    request.session.modified = True
    response = HttpResponse()
    response["HX-Redirect"] = reverse(
        "fundingrequests:doi_preview_detail", kwargs={"session_key": session_key}
    )
    return response


@require_session()
@login_required
@require_POST
def doi_preview_reset_type(request: HttpRequest, session_key: str) -> HttpResponse:
    """HTMX endpoint: Reset publication type override to original auto-detected type.

    Clears any journal_id/publisher_id override from session, re-derives the
    original type from original_metadata, and issues HX-Redirect to the preview page.
    """
    session_data = request.session[session_key]

    override = _load_override(session_data)
    override = override.drop_publication_type()
    _dump_override(session_data, override)

    request.session[session_key] = session_data
    request.session.modified = True
    response = HttpResponse()
    response["HX-Redirect"] = reverse(
        "fundingrequests:doi_preview_detail", kwargs={"session_key": session_key}
    )
    return response


class DeleteFunding(CodaBaseDto):
    funder: str
    project_id: str


class AddFunding(CodaBaseDto):
    funder_id: int
    project_id: str


def _render_funding_partial(request: HttpRequest, session_key: str) -> HttpResponse:
    """Build and render the funding partial from session data.

    Rebuilds the preview DTO from session (same logic as DOIPreviewDetailView)
    so the returned HTML reflects the current override state.
    """
    session_data = request.session[session_key]

    doi = Doi(session_data["doi"])
    metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
    doi_service = DOIImportService(
        doi_client=DOIPreviewDetailView.doi_client, metadata_cache={doi: metadata}
    )
    override = _load_override(session_data)

    if override:
        preview_dto = doi_service.preview_with_override(doi, override)
    else:
        preview_dto = doi_service.fetch_doi_preview(doi)

    funding_orgs = FundingOrganization.objects.all()
    funding = tag_existing_funders(preview_dto.publication.funding)
    context = {
        "funding": funding,
        "session_key": session_key,
        "funding_organizations": funding_orgs,
    }
    return render(request, "fundingrequests/partials/doi_import_publication_funding.html", context)


@require_session()
@login_required
@require_POST
def doi_preview_delete_funding(request: HttpRequest, session_key: str) -> HttpResponse:
    session = request.session[session_key]

    delete = formdata.map_to_model(DeleteFunding, request.POST)
    override = _load_override(session)
    override = override.remove_funding(delete.funder, delete.project_id)
    _dump_override(session, override)
    request.session.modified = True

    return _render_funding_partial(request, session_key)


@require_session()
@login_required
@require_POST
def doi_preview_add_funding(request: HttpRequest, session_key: str) -> HttpResponse:
    session = request.session[session_key]

    add = formdata.map_to_model(AddFunding, request.POST)
    override = _load_override(session)
    override = override.add_funding(
        [OverrideFunding(FundingOrganizationId(add.funder_id), add.project_id)]
    )
    _dump_override(session, override)
    request.session.modified = True

    return _render_funding_partial(request, session_key)


@require_session()
@login_required
@require_POST
def doi_preview_reset_funding(request: HttpRequest, session_key: str) -> HttpResponse:
    session_data = request.session[session_key]

    override = _load_override(session_data)
    override = override.reset_funding()
    _dump_override(session_data, override)
    request.session.modified = True

    return _render_funding_partial(request, session_key)

"""DOI Import Preview Views.

Handles the preview workflow for DOI imports:
1. DOI input → fetch metadata → create session
2. Preview detail page (session-based, not persisted)
3. Edit workflows (update session, not database)
4. Final save (persist to database)
"""

from typing import ClassVar
from uuid import uuid4

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from coda.apps.publications.dto import PublicationDto
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.publication.services.doi_client import CrossrefDoiClient, DOIMetadataClient
from coda.contexts.publication.services.doi_import_service import DOIImportService
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
            creation_dto = doi_service.prepare_funding_request_dto(doi)

            # Store in session using to_post_data() for form-compatible serialization
            # Note: We store fields individually because publication is polymorphic (PublicationDto vs MonographDto)
            # and Pydantic can't deserialize abstract base types without discriminators
            session_key = f"doi_preview_{uuid4()}"
            request.session[session_key] = {
                "publication": creation_dto.publication.to_post_data(),
                "payment": creation_dto.payment.to_post_data(),
                "funding": [f.to_post_data() for f in creation_dto.funding],
                "extra_information": creation_dto.extra_information.to_post_data(),
            }

            # Redirect to preview detail page
            return redirect("fundingrequests:doi_preview_detail", session_key=session_key)

        except Exception as e:
            # Handle errors and re-display form with error message
            context = {
                "error": f"Failed to import DOI: {str(e)}",
            }
            return render(request, "fundingrequests/doi_import_input.html", context)


class DOIPreviewDetailView(View):
    """Display preview detail page loading data from session (not database)."""

    def get(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Load preview data from session and display detail page.

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Rendered preview detail page
        """
        from coda.apps.fundingrequests.queries.preview_context_builder import build_preview_context

        # Load preview data from session
        preview_data = request.session.get(session_key)

        if not preview_data:
            # Handle missing session data (expired or invalid key)
            return HttpResponse("Preview session not found or expired", status=404)

        # Build context from DTOs
        context = build_preview_context(preview_data, session_key)

        # Add edit URLs (placeholder for now - will be wizard URLs)
        # TODO: Replace with actual DOI import wizard URLs when they're implemented
        context["edit_publication_url"] = f"#edit-publication-{session_key}"
        context["edit_funding_url"] = f"#edit-funding-{session_key}"
        context["edit_submitter_url"] = f"#edit-submitter-{session_key}"

        return render(request, "fundingrequests/doi_preview_detail.html", context)


class DOIPreviewSaveView(View):
    """Persist preview session data to database and redirect to real detail page."""

    def post(self, request: HttpRequest, session_key: str) -> HttpResponse:
        """
        Save preview data from session to database.

        Workflow:
        1. Load preview data from session
        2. Reconstruct DTOs
        3. Create FundingRequest using service
        4. Clean up session
        5. Redirect to real detail page

        Args:
            session_key: The session key where preview data is stored

        Returns:
            Redirect to funding request detail page
        """
        # Load preview data from session
        preview_data = request.session.get(session_key)

        if not preview_data:
            return HttpResponse("Preview session not found or expired", status=404)

        # Reconstruct DTOs from session data
        # Note: We reconstruct explicitly because publication is polymorphic (abstract base type)
        # For DOI imports, publication is always PublicationDto (articles)
        publication_dto = PublicationDto.model_validate(preview_data["publication"])
        creation_dto = CreateFundingRequestDto(
            publication=publication_dto,
            payment=PaymentDto.model_validate(preview_data["payment"]),
            funding=[ExternalFundingDto.model_validate(f) for f in preview_data["funding"]],
            extra_information=ExtraInformationDto.model_validate(preview_data["extra_information"]),
        )

        # Persist to database using service
        fr_id = fundingrequests.create_fundingrequest(creation_dto)

        # Clean up session
        del request.session[session_key]

        # Redirect to real detail page
        return redirect("fundingrequests:detail", pk=fr_id)

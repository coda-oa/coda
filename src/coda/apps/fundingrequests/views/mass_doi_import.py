"""Mass DOI Import Views.

Workflow:
1. MassDOIImportInputView — textarea for multiple DOIs → batch fetch → create sessions
2. MassDOIPreviewView — summary list with per-DOI status and "View details" links
3. MassDOIPreviewSaveView — import all successful DOIs with overrides → redirect to result
4. MassDOIImportResultView — display import result summary (GET only)
"""

from typing import Any, ClassVar
from uuid import uuid4

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from coda.contexts.fundingrequest.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.fundingrequest.services.doi_import.doi_client import (
    CachingDOIMetadataClient,
    DOIMetadataClient,
    crossref,
)
from coda.contexts.fundingrequest.services.doi_import._service import (
    OverrideImport,
    OverrideImportTypeAdapter,
)
from coda.contexts.fundingrequest.services.doi_import._mass_service import (
    MassDOIImportService,
)
from coda.domain.publication.links import Doi


def _make_child_session_data(
    doi: Doi,
    metadata: ExternalPublicationMetadata,
    pub_type: str,
    *,
    mass_import_session_key: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "doi": str(doi),
        "original_metadata": metadata.model_dump(mode="json"),
        "publication_type": pub_type,
        "override": OverrideImportTypeAdapter.dump_python(OverrideImport.empty(), mode="json"),
    }
    if mass_import_session_key is not None:
        data["mass_import_session_key"] = mass_import_session_key
    return data


class MassDOIImportInputView(LoginRequiredMixin, View):
    """Accept multiple DOIs via textarea, validate, batch fetch, redirect to preview."""

    doi_client: ClassVar[DOIMetadataClient] = crossref

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "fundingrequests/mass_doi_import_input.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        raw_text = request.POST.get("dois", "").strip()
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

        if not lines:
            return render(
                request,
                "fundingrequests/mass_doi_import_input.html",
                {"error": "Please enter at least one DOI."},
            )

        valid_dois: list[Doi] = []
        invalid_count = 0
        seen = set()
        duplicate_count = 0

        for line in lines:
            try:
                doi = Doi(line)
                doi_str = str(doi)
                if doi_str in seen:
                    duplicate_count += 1
                else:
                    seen.add(doi_str)
                    valid_dois.append(doi)
            except ValueError:
                invalid_count += 1

        if not valid_dois:
            return render(
                request,
                "fundingrequests/mass_doi_import_input.html",
                {"error": "No valid DOIs were found in your input."},
            )

        service = MassDOIImportService(doi_client=self.doi_client)
        preview = service.fetch_multi(valid_dois)

        mass_session_key = f"mass_doi_import_{uuid4()}"
        mass_session_data: dict[str, Any] = {
            "results": [],
            "skipped_invalid": invalid_count,
            "skipped_duplicates": duplicate_count,
        }

        for single in preview.successes:
            child_key = f"doi_preview_{uuid4()}"
            request.session[child_key] = _make_child_session_data(
                single.doi,
                single.metadata,
                single.publication_type,
                mass_import_session_key=mass_session_key,
            )
            mass_session_data["results"].append(
                {
                    "doi": str(single.doi),
                    "status": "success",
                    "publication_type": single.publication_type,
                    "title": single.metadata.title,
                    "child_key": child_key,
                    "warnings": single.warnings,
                }
            )

        for err in preview.errors:
            mass_session_data["results"].append(
                {
                    "doi": str(err.doi),
                    "status": "error",
                    "error": err.error,
                }
            )

        request.session[mass_session_key] = mass_session_data
        request.session.modified = True

        return redirect("fundingrequests:mass_doi_preview", session_key=mass_session_key)


class MassDOIPreviewView(LoginRequiredMixin, View):
    """Display mass import preview list with per-DOI status and override hints."""

    doi_client: ClassVar[DOIMetadataClient] = crossref

    def get(self, request: HttpRequest, session_key: str) -> HttpResponse:
        session_data = request.session.get(session_key)
        if not session_data:
            return HttpResponse("Preview session not found or expired", status=404)

        results = session_data.get("results", [])

        # Check override status and set row class for each result
        for result in results:
            result["row_class"] = "success" if result["status"] == "success" else "error"
            if result["status"] == "success":
                child_key = result.get("child_key")
                if child_key:
                    child = request.session.get(child_key)
                    if child:
                        override = child.get("override", {})
                        has_override = any(v not in (None, [], {}) for v in override.values())
                        result["has_overrides"] = has_override
                    else:
                        result["has_overrides"] = False
                else:
                    result["has_overrides"] = False

        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] == "error")
        warning_count = sum(1 for r in results if r.get("warnings"))

        context = {
            "session_key": session_key,
            "results": results,
            "success_count": success_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "skipped_invalid": session_data.get("skipped_invalid", 0),
            "skipped_duplicates": session_data.get("skipped_duplicates", 0),
        }

        return render(request, "fundingrequests/mass_doi_preview.html", context)


class MassDOIPreviewSaveView(LoginRequiredMixin, View):
    """Import all successful DOIs, applying overrides from child sessions."""

    doi_client: ClassVar[DOIMetadataClient] = crossref

    def post(self, request: HttpRequest, session_key: str) -> HttpResponse:
        session_data = request.session.get(session_key)
        if not session_data:
            return HttpResponse("Preview session not found or expired", status=404)

        results = session_data.get("results", [])
        caching_client = CachingDOIMetadataClient(self.doi_client)
        service = MassDOIImportService(doi_client=caching_client)

        # Build inputs from child sessions
        dois_and_overrides: list[tuple[Doi, OverrideImport]] = []
        metadata_cache: dict[Doi, ExternalPublicationMetadata] = {}
        pre_failed: list[tuple[str, str]] = []  # structural failures (no child session)

        for result in results:
            if result["status"] != "success":
                continue

            doi = Doi(result["doi"])
            child_key = result.get("child_key")
            if not child_key:
                pre_failed.append((str(doi), "Missing child session"))
                continue

            child = request.session.get(child_key)
            if not child:
                pre_failed.append((str(doi), "Child session expired"))
                continue

            metadata = ExternalPublicationMetadata.model_validate(child["original_metadata"])
            override = self._load_override_from_session(child)
            dois_and_overrides.append((doi, override))
            metadata_cache[doi] = metadata

            del request.session[child_key]

        # Delegate import to service
        import_result = service.import_multi(dois_and_overrides, metadata_cache)

        # Clean up parent session
        del request.session[session_key]
        request.session.modified = True

        # Translate to template context
        import_links: list[dict[str, Any]] = []
        for doi, fr_id in import_result.imported:
            title = getattr(metadata_cache.get(doi), "title", str(doi))
            import_links.append(
                {
                    "url": reverse("fundingrequests:detail", kwargs={"pk": fr_id}),
                    "title": title,
                    "doi": str(doi),
                }
            )

        skipped = [(str(doi), reason) for doi, reason in import_result.skipped]
        failed = pre_failed + [(str(doi), reason) for doi, reason in import_result.failed]

        result_key = f"mass_import_result_{uuid4()}"
        request.session[result_key] = {
            "import_links": import_links,
            "skipped": skipped,
            "failed": failed,
            "imported_count": len(import_links),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
        }
        request.session.modified = True

        return redirect("fundingrequests:mass_doi_result", result_key=result_key)

    def _load_override_from_session(self, child_session: dict[str, object]) -> OverrideImport:
        """Reconstruct OverrideImport from child session data.

        Uses the same OverrideImportTypeAdapter as the single-DOI flow,
        ensuring consistent serialization regardless of which view wrote it.
        """
        raw_override = child_session.get("override", {})
        if isinstance(raw_override, dict):
            return OverrideImportTypeAdapter.validate_python(raw_override)
        return OverrideImport.empty()


class MassDOIImportResultView(LoginRequiredMixin, View):
    """Display the mass import result summary.

    Loads result data from a temporary session key (stored by
    MassDOIPreviewSaveView), renders it once, then cleans up the session.
    """

    def get(self, request: HttpRequest, result_key: str) -> HttpResponse:
        result_data = request.session.get(result_key)
        if not result_data:
            return HttpResponse("Result session not found or expired", status=404)

        del request.session[result_key]
        request.session.modified = True

        return render(request, "fundingrequests/mass_doi_result.html", result_data)

"""Mass DOI Import Service - Batch fetch and import multiple DOIs.

Relies on DOIMetadataClient.fetch_publications_batch() for batch fetching
and DOIImportService for per-DOI import during batch save.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services._map_to_preview import (
    build_preview_article,
    build_preview_monograph,
)
from coda.contexts.publication.services.doi_client import DOIMetadataClient
from coda.contexts.publication.services.doi_client._crossref._crossref_type_detector import (
    detect_publication_type,
)
from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideImport,
)
from coda.contexts.publication.services.doi_client.errors import DOIFetchError, DOINotFoundError
from coda.contexts.publication.services.errors import DOIAlreadyImported, InvalidMetadataError
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.publication.links import Doi


@dataclass
class SingleDOIPreview:
    """Preview data for a single successfully fetched DOI.

    The ``warnings`` list is populated by building a
    ``PreviewArticle``/``PreviewMonograph`` from the raw metadata and
    extracting its ``.warnings`` property, keeping the detection logic
    centralized in the preview DTOs rather than duplicating it here.
    """

    doi: Doi
    metadata: ExternalPublicationMetadata
    publication_type: str  # "article" | "monograph"
    warnings: list[str] = field(default_factory=list)


@dataclass
class SingleDOIError:
    """Error data for a single DOI that failed to fetch."""

    doi: Doi
    error: str


@dataclass
class MassImportPreview:
    """Result of a batch DOI fetch."""

    successes: list[SingleDOIPreview] = field(default_factory=list)
    errors: list[SingleDOIError] = field(default_factory=list)


@dataclass
class MassImportResult:
    """Result of a mass import save."""

    imported: list[tuple[Doi, FundingRequestId]] = field(default_factory=list)
    skipped: list[tuple[Doi, str]] = field(default_factory=list)  # (doi, reason)
    failed: list[tuple[Doi, str]] = field(default_factory=list)  # (doi, reason)


class MassDOIImportService:
    """Orchestrate batch fetching and importing of multiple DOIs."""

    def __init__(self, doi_client: DOIMetadataClient) -> None:
        self.doi_client = doi_client

    def fetch_multi(self, dois: list[Doi]) -> MassImportPreview:
        """Fetch metadata for multiple DOIs via batch call.

        Args:
            dois: List of DOIs to fetch

        Returns:
            MassImportPreview with per-DOI success/error results
        """
        results = self.doi_client.fetch_publications_batch(dois)

        preview = MassImportPreview()
        for doi_str, result in results.items():
            doi = Doi(doi_str)
            if isinstance(result, ExternalPublicationMetadata):
                pub_type = detect_publication_type(result)
                # Reuse the centralized warning detection from PreviewArticle / PreviewMonograph
                # to avoid re-implementing journal/publisher missing checks.
                warnings: list[str] = []
                if pub_type == "article":
                    warnings = build_preview_article(doi, result).warnings
                elif pub_type == "monograph":
                    warnings = build_preview_monograph(doi, result).warnings

                preview.successes.append(
                    SingleDOIPreview(
                        doi=doi,
                        metadata=result,
                        publication_type=pub_type,
                        warnings=warnings,
                    )
                )
            else:
                preview.errors.append(SingleDOIError(doi=doi, error=str(result)))

        return preview

    def import_multi(
        self,
        dois_and_overrides: list[tuple[Doi, OverrideImport]],
        metadata_cache: dict[Doi, ExternalPublicationMetadata],
    ) -> MassImportResult:
        """Import multiple DOIs, applying per-DOI overrides.

        Uses DOIImportService under the hood with a pre-populated metadata cache
        to avoid re-fetching from Crossref.

        Args:
            dois_and_overrides: List of (doi, override) pairs
            metadata_cache: Pre-fetched metadata keyed by DOI

        Returns:
            MassImportResult with per-DOI outcome
        """
        result = MassImportResult()

        for doi, override in dois_and_overrides:
            cache = {doi: metadata_cache[doi]} if doi in metadata_cache else {}
            service = DOIImportService(doi_client=self.doi_client, metadata_cache=cache)
            try:
                fr_id = service.import_from_doi(doi, override)
                result.imported.append((doi, fr_id))
            except DOIAlreadyImported as e:
                result.skipped.append((doi, str(e)))
            except (DOINotFoundError, DOIFetchError, InvalidMetadataError) as e:
                result.failed.append((doi, str(e)))
            except Exception as e:
                result.failed.append((doi, str(e)))

        return result

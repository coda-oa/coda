"""Mass DOI Import Service - Batch fetch and import multiple DOIs.

Relies on DOIMetadataClient.fetch_publications_batch() for batch fetching
and DOIImportService for per-DOI import during batch save.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services._map_to_preview import (
    build_preview_article,
    build_preview_monograph,
)
from coda.contexts.publication.services.doi_client import (
    CachingDOIMetadataClient,
    DOIMetadataClient,
)
from coda.contexts.publication.services.doi_client._crossref._crossref_type_detector import (
    detect_publication_type,
)
from coda.contexts.publication.services.doi_client.errors import DOIFetchError, DOINotFoundError
from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideImport,
)
from coda.contexts.publication.services.doi_repository_uow import UnitOfWorkDOIRepository
from coda.contexts.publication.services.errors import DOIAlreadyImported, InvalidMetadataError
from coda.contexts.publication.services.ror_client import CachingRORClient, RORClient
from coda.contexts.publication.services.ror_client.exceptions import RORClientError
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.publication.links import CrossrefId, Doi

logger = logging.getLogger(__name__)


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
        ror_client: CachingRORClient | RORClient | None = None,
    ) -> MassImportResult:
        """Import multiple DOIs, applying per-DOI overrides.

        Uses a single ``DOIImportService`` backed by a
        ``UnitOfWorkDOIRepository`` so that all database writes are
        deferred and flushed in bulk on commit.  The ``doi_client`` is
        wrapped in a ``CachingDOIMetadataClient`` to avoid duplicate
        HTTP requests for funder DOIs shared across publications.

        Args:
            dois_and_overrides: List of (doi, override) pairs
            metadata_cache: Pre-fetched metadata keyed by DOI

        Returns:
            MassImportResult with per-DOI outcome
        """
        caching_client = CachingDOIMetadataClient(self.doi_client)
        ror_client = ror_client or CachingRORClient(RORClient())

        uow = UnitOfWorkDOIRepository(ror_client=ror_client)

        uow.prewarm_doi_cache([doi for doi, _ in dois_and_overrides])

        # Pre-warm ROR cache for all funders before import to avoid
        # on-demand API calls during per-DOI processing.
        crossref_ids = _collect_crossref_ids(metadata_cache)
        if crossref_ids:
            try:
                ror_client.resolve_by_ids([CrossrefId(cid) for cid in crossref_ids])
            except RORClientError:
                logger.warning(
                    "ROR batch resolution failed for %d IDs — will resolve on demand during import",
                    len(crossref_ids),
                    exc_info=True,
                )

        service = DOIImportService(
            doi_client=caching_client,
            repo=uow,
            metadata_cache=metadata_cache,
        )

        result = MassImportResult()
        seen_before_commit: list[Doi] = []

        for doi, override in dois_and_overrides:
            try:
                service.import_from_doi(doi, override)
                seen_before_commit.append(doi)
            except DOIAlreadyImported as e:
                result.skipped.append((doi, str(e)))
            except (DOINotFoundError, DOIFetchError, InvalidMetadataError) as e:
                logger.error("DOI import failed for %s: %s", doi, e, exc_info=True)
                result.failed.append((doi, str(e)))
            except Exception as e:
                logger.exception("Unexpected error importing DOI %s", doi)
                result.failed.append((doi, str(e)))

        try:
            fr_ids = uow.commit()
        except Exception as e:
            logger.exception("Batch commit failed for %d DOIs", len(seen_before_commit))
            for doi in seen_before_commit:
                result.failed.append((doi, f"Commit failed: {e}"))
            return result

        for doi, fr_id in zip(seen_before_commit, fr_ids):
            result.imported.append((doi, fr_id))

        logger.info(
            "Mass import complete: %d imported, %d skipped, %d failed",
            len(result.imported),
            len(result.skipped),
            len(result.failed),
        )
        return result


def _collect_crossref_ids(
    metadata_cache: dict[Doi, ExternalPublicationMetadata],
) -> set[str]:
    """Extract all numeric Crossref IDs from metadata funder identifiers."""
    ids: set[str] = set()
    for meta in metadata_cache.values():
        for funder in meta.funders:
            for id_ in funder.funder.identifiers:
                if id_.isdigit():
                    ids.add(id_)
    return ids

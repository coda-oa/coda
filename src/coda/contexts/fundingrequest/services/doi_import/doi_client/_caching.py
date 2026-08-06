"""Caching decorator for DOIMetadataClient.

Wraps any DOIMetadataClient with in-memory caches to avoid redundant
HTTP requests within a single session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coda.contexts.fundingrequest.dto.external_metadata import (
    ExternalPublicationMetadata,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client.errors import DOINotFoundError
from coda.domain.publication.links import Doi

if TYPE_CHECKING:
    from coda.contexts.fundingrequest.services.doi_import.doi_client._doi_client import (
        DOIMetadataClient,
    )

_NF: None = None  # sentinel cached when a DOI is not found


class CachingDOIMetadataClient:
    """Wraps a DOIMetadataClient with in-memory caching for fetch methods.

    ``fetch_publication`` results are cached by DOI.
    ``fetch_publications_batch`` delegates to the inner client and caches
    each successful result individually so subsequent single-DOI lookups
    also benefit.

    Not-found DOIs (``DOINotFoundError``) are also cached (negative caching)
    so they are never re-queried within the same session.
    """

    def __init__(self, inner: DOIMetadataClient) -> None:
        self._inner = inner
        self._pub_cache: dict[Doi, ExternalPublicationMetadata | None] = {}

    def fetch_publication(self, doi: Doi) -> ExternalPublicationMetadata:
        if doi not in self._pub_cache:
            try:
                self._pub_cache[doi] = self._inner.fetch_publication(doi)
            except DOINotFoundError:
                self._pub_cache[doi] = _NF
                raise
        result = self._pub_cache[doi]
        if result is _NF:
            raise DOINotFoundError(doi)
        return result

    def fetch_publications_batch(
        self, dois: list[Doi]
    ) -> dict[str, ExternalPublicationMetadata | Exception]:
        results = self._inner.fetch_publications_batch(dois)
        for doi_str, result in results.items():
            if isinstance(result, ExternalPublicationMetadata):
                self._pub_cache[Doi(doi_str)] = result
            elif isinstance(result, DOINotFoundError):
                self._pub_cache[Doi(doi_str)] = _NF
        return results

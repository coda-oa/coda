"""Caching decorator for DOIMetadataClient.

Wraps any DOIMetadataClient with in-memory caches for all three methods
to avoid redundant HTTP requests within a single session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coda.contexts.publication.dto.external_metadata import (
    ExternalFundingOrganisationMetadata,
    ExternalPublicationMetadata,
)
from coda.domain.publication.links import Doi

if TYPE_CHECKING:
    from coda.contexts.publication.services.doi_client._doi_client import DOIMetadataClient


class CachingDOIMetadataClient:
    """Wraps a DOIMetadataClient with in-memory caching for all fetch methods.

    ``fetch_publication`` and ``fetch_funder`` results are cached by DOI.
    ``fetch_publications_batch`` delegates to the inner client and caches
    each successful result individually so subsequent single-DOI lookups
    also benefit.
    """

    def __init__(self, inner: DOIMetadataClient) -> None:
        self._inner = inner
        self._pub_cache: dict[Doi, ExternalPublicationMetadata] = {}
        self._funder_cache: dict[Doi, ExternalFundingOrganisationMetadata] = {}

    def fetch_publication(self, doi: Doi) -> ExternalPublicationMetadata:
        if doi not in self._pub_cache:
            self._pub_cache[doi] = self._inner.fetch_publication(doi)
        return self._pub_cache[doi]

    def fetch_funder(self, doi: Doi) -> ExternalFundingOrganisationMetadata:
        if doi not in self._funder_cache:
            self._funder_cache[doi] = self._inner.fetch_funder(doi)
        return self._funder_cache[doi]

    def fetch_publications_batch(
        self, dois: list[Doi]
    ) -> dict[str, ExternalPublicationMetadata | Exception]:
        results = self._inner.fetch_publications_batch(dois)
        for doi_str, result in results.items():
            if isinstance(result, ExternalPublicationMetadata):
                self._pub_cache[Doi(doi_str)] = result
        return results

"""Funder Resolution Service - resolves funder names by Crossref ID via ROR API.

This service is separate from the DOI metadata client because ROR
identifiers (Crossref IDs) are distinct from publication DOIs and follow
a different resolution protocol.
"""

from __future__ import annotations

from coda.contexts.publication.services.doi_client._ror import RORClient
from coda.domain.publication.links import CrossrefId


class FunderResolutionService:
    """Resolves funder names by Crossref ID via the ROR API.

    Maintains an internal cache so repeated lookups don't re-query the API.
    """

    def __init__(self, ror_client: RORClient | None = None) -> None:
        self._ror = ror_client or RORClient()
        self._cache: dict[str, str] = {}

    def resolve_funders(self, crossref_ids: set[str]) -> dict[str, str]:
        """Resolve funder names by Crossref ID via ROR API.

        Queries the ROR API for uncached IDs and returns a
        ``dict[str, str]`` mapping crossref_id → resolved name.

        Results are cached so repeated calls don't re-query the API.
        """
        uncached = {cid for cid in crossref_ids if cid not in self._cache}

        if uncached:
            links = [CrossrefId(cid) for cid in uncached]
            ror_results = self._ror.resolve_by_ids(links)
            for cid in uncached:
                if cid in ror_results:
                    self._cache[cid] = ror_results[cid].name

        return {cid: self._cache[cid] for cid in crossref_ids if cid in self._cache}

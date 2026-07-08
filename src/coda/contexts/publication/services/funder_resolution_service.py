"""Funder Resolution Service - resolves funder names by Crossref ID via ROR API.

This service wraps a ``RORClient`` in a ``CachingRORClient`` to provide
transparent caching.  Callers never need to manage a pre-resolution step
or pass around a name map.
"""

from __future__ import annotations

from coda.contexts.publication.services.doi_client._ror import CachingRORClient, RORClient
from coda.domain.publication.links import CrossrefId


class FunderResolutionService:
    """Resolves funder names by Crossref ID via the ROR API.

    Delegates both resolution and caching to the underlying ROR client,
    which is automatically wrapped in a ``CachingRORClient``.
    """

    def __init__(self, ror_client: RORClient | None = None) -> None:
        self._ror = CachingRORClient(ror_client or RORClient())

    def resolve_funders(self, crossref_ids: set[str]) -> dict[str, str]:
        """Resolve funder names by Crossref ID via ROR API.

        Args:
            crossref_ids: Set of Crossref numeric identifier strings.

        Returns:
            Mapping of crossref_id → resolved funder name.
        """
        if not crossref_ids:
            return {}

        links = [CrossrefId(cid) for cid in crossref_ids]
        ror_results = self._ror.resolve_by_ids(links)

        return {cid: ror_results[cid].name for cid in crossref_ids if cid in ror_results}

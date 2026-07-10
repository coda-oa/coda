"""Caching decorator for RORClient.

Wraps any RORClient with an in-memory cache to avoid redundant
API calls within a single session.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from coda.contexts.publication.services.ror_client.exceptions import RORClientError
from coda.domain.publication.links import Link

from .ror_client import RORClient, RORRecord


class CachingRORClient:
    """Wraps a RORClient with in-memory caching for ``resolve_by_ids``.

    Both successful and empty results are cached by the string representation
    of each input link, so identifiers that don't match any ROR record are
    never re-queried.
    """

    def __init__(self, inner: RORClient) -> None:
        self._inner = inner
        self._cache: dict[str, RORRecord | None] = {}

    def resolve_by_ids(self, links: Sequence[Link]) -> dict[str, RORRecord]:
        """Resolve funder identifiers, using cache to avoid redundant API calls.

        Unresolved (uncached) identifiers are forwarded to the inner client.
        Both matched and unmatched results are cached so subsequent lookups
        for the same identifier return instantly.
        """
        uncached = [link for link in links if str(link) not in self._cache]
        if uncached:
            try:
                results = self._inner.resolve_by_ids(uncached)
            except RORClientError:
                raise
            self._cache.update(results)
            # Mark queried-but-not-found IDs as None so they are never retried
            for link in uncached:
                key = str(link)
                if key not in self._cache:
                    self._cache[key] = None

        return {
            str(link): cast(RORRecord, self._cache[str(link)])
            for link in links
            if self._cache.get(str(link)) is not None
        }

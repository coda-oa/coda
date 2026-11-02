"""Batch fetch publication metadata from Crossref using filter parameter.

Uses the Crossref /works endpoint with filter=doi:X,doi:Y,... to fetch
multiple works in a single API call. Supports cursor-based pagination
for large result sets.
"""

import logging
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from coda.contexts.fundingrequest.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.fundingrequest.services.doi_import.doi_client.errors import (
    DOINotFoundError,
    map_to_doi_error,
)
from coda.domain.publication.links import Doi

from ._fetch_publication import CROSSREF_API_BASE, _parse_crossref_response, _resolve_politeness
from ._politeness import CrossrefPoliteness
from ._token_validity import AUTH_REJECT_STATUSES, mark_token_invalid

logger = logging.getLogger(__name__)


class HttpGetClient(Protocol):
    """Something with a .get() method compatible with httpx.

    The return value is loosely typed because the function only calls
    .raise_for_status().json() on it — any object satisfying that
    interface works (httpx.Response in production, custom fakes in tests).
    """

    def get(
        self,
        url: str,
        *,
        params: Any,
        headers: dict[str, str] | None = None,
        timeout: int,
        follow_redirects: bool,
    ) -> Any: ...


def fetch_publications_batch(
    dois: Sequence[Doi],
    timeout: int = 30,
    *,
    politeness: CrossrefPoliteness | None = None,
    http_client: HttpGetClient | None = None,
) -> dict[str, ExternalPublicationMetadata | Exception]:
    """Fetch publication metadata for multiple DOIs in a single batch call.

    Uses Crossref's filter parameter: ?filter=doi:VALUE1,doi:VALUE2,...
    with cursor-based pagination to handle large result sets.

    Args:
        dois: The DOIs to fetch metadata for
        timeout: HTTP request timeout in seconds
        politeness: Explicit access credentials. When None, credentials are
            resolved from the global preferences (see /preferences/).

    Returns:
        Dict keyed by DOI string. Each value is either ExternalPublicationMetadata
        on success, or an Exception (DOINotFoundError, DOIFetchError) on failure.
    """
    if not dois:
        return {}

    client: Any = http_client or httpx

    resolved = _resolve_politeness(politeness)
    params: dict[str, str | int] = {
        "filter": ",".join(f"doi:{doi}" for doi in dois),
        "rows": len(dois),
        "cursor": "*",
        **resolved.query_params(),
    }
    headers = resolved.headers()

    # Safety cap: at most one item per requested DOI can match,
    # so len(dois) pages is a generous upper bound.
    items, error = _fetch_all_pages(client, params, headers, len(dois), timeout)

    if (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code in AUTH_REJECT_STATUSES
        and "Crossref-Plus-API-Token" in headers
    ):
        mark_token_invalid()

    found = _parse_batch_items(items)
    return _build_batch_results(dois, found, error)


def _fetch_all_pages(
    client: Any,
    params: dict[str, str | int],
    headers: dict[str, str],
    max_pages: int,
    timeout: int,
) -> tuple[list[dict[str, Any]], Exception | None]:
    """Fetch all pages of batch data from Crossref.

    Iterates through cursor-based pagination up to *max_pages* calls.

    Returns a tuple of ``(items, error)``. If a page fails after earlier pages
    succeeded, the items already collected are preserved and the error is
    returned alongside them, so the caller can still resolve the DOIs found on
    earlier pages instead of failing the entire batch.
    """
    all_items: list[dict[str, Any]] = []
    for _ in range(max_pages):
        try:
            response = client.get(
                CROSSREF_API_BASE,
                params=params,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            ).raise_for_status()
        except Exception as e:
            return all_items, e
        data = response.json()

        message = data.get("message", {})
        items: list[Any] = message.get("items", [])
        if not items:
            break
        all_items.extend(items)

        next_cursor = message.get("next-cursor")
        if not next_cursor:
            break
        params["cursor"] = next_cursor

    return all_items, None


def _parse_batch_items(
    items: list[dict[str, Any]],
) -> dict[str, ExternalPublicationMetadata]:
    """Parse raw Crossref items into a dict keyed by DOI string.

    Individual parse failures are logged and skipped.
    """
    found: dict[str, ExternalPublicationMetadata] = {}
    for item in items:
        doi_str = item.get("DOI", "")
        if not doi_str:
            continue
        try:
            found[doi_str] = _parse_crossref_response({"message": item})
        except Exception as e:
            logger.warning("Failed to parse Crossref item for DOI %s: %s", doi_str, e)
    return found


def _build_batch_results(
    dois: Sequence[Doi],
    found: dict[str, ExternalPublicationMetadata],
    error: Exception | None = None,
) -> dict[str, ExternalPublicationMetadata | Exception]:
    """Build the final result dict for every requested DOI.

    DOIs present in *found* get their metadata. Missing DOIs get a
    :class:`DOINotFoundError`, unless a page failed partway through the batch
    (``error`` is set), in which case they get the mapped error instead.
    """
    results: dict[str, ExternalPublicationMetadata | Exception] = {}
    for doi in dois:
        doi_str = str(doi)
        if doi_str in found:
            results[doi_str] = found[doi_str]
        elif error is not None:
            results[doi_str] = map_to_doi_error(error, doi)
        else:
            results[doi_str] = DOINotFoundError(doi)
    return results

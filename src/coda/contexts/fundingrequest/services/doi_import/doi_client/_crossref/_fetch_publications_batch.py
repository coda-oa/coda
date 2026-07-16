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

from ._fetch_publication import CROSSREF_API_BASE, _parse_crossref_response

logger = logging.getLogger(__name__)


class HttpGetClient(Protocol):
    """Something with a .get() method compatible with httpx.

    The return value is loosely typed because the function only calls
    .raise_for_status().json() on it — any object satisfying that
    interface works (httpx.Response in production, custom fakes in tests).
    """

    def get(self, url: str, *, params: Any, timeout: int, follow_redirects: bool) -> Any: ...


def fetch_publications_batch(
    dois: Sequence[Doi],
    timeout: int = 30,
    *,
    http_client: HttpGetClient | None = None,
) -> dict[str, ExternalPublicationMetadata | Exception]:
    """Fetch publication metadata for multiple DOIs in a single batch call.

    Uses Crossref's filter parameter: ?filter=doi:VALUE1,doi:VALUE2,...
    with cursor-based pagination to handle large result sets.

    Args:
        dois: The DOIs to fetch metadata for
        timeout: HTTP request timeout in seconds

    Returns:
        Dict keyed by DOI string. Each value is either ExternalPublicationMetadata
        on success, or an Exception (DOINotFoundError, DOIFetchError) on failure.
    """
    if not dois:
        return {}

    client: Any = http_client or httpx

    filter_value = ",".join(f"doi:{doi}" for doi in dois)
    params: dict[str, str | int] = {
        "filter": filter_value,
        "rows": len(dois),
        "cursor": "*",
    }

    # Safety cap: at most one item per requested DOI can match,
    # so len(dois) pages is a generous upper bound.
    try:
        items = _fetch_all_pages(client, params, len(dois), timeout)
    except Exception as e:
        return {str(doi): map_to_doi_error(e, doi) for doi in dois}

    found = _parse_batch_items(items)
    return _build_batch_results(dois, found)


def _fetch_all_pages(
    client: Any,
    params: dict[str, str | int],
    max_pages: int,
    timeout: int,
) -> list[dict[str, Any]]:
    """Fetch all pages of batch data from Crossref.

    Iterates through cursor-based pagination up to *max_pages* calls.
    Raises on HTTP or network error; the caller maps the exception
    to per-DOI error results.
    """
    all_items: list[dict[str, Any]] = []
    for _ in range(max_pages):
        response = client.get(
            CROSSREF_API_BASE,
            params=params,
            timeout=timeout,
            follow_redirects=True,
        ).raise_for_status()
        data = response.json()

        message = data.get("message", {})
        items = message.get("items", [])
        if not items:
            break
        all_items.extend(items)

        next_cursor = message.get("next-cursor")
        if not next_cursor:
            break
        params["cursor"] = next_cursor

    return all_items


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
) -> dict[str, ExternalPublicationMetadata | Exception]:
    """Build the final result dict for every requested DOI.

    DOIs present in *found* get their metadata; missing DOIs get a
    :class:`DOINotFoundError`.
    """
    results: dict[str, ExternalPublicationMetadata | Exception] = {}
    for doi in dois:
        doi_str = str(doi)
        if doi_str in found:
            results[doi_str] = found[doi_str]
        else:
            results[doi_str] = DOINotFoundError(doi)
    return results

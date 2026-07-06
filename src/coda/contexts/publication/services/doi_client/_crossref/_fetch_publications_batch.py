"""Batch fetch publication metadata from Crossref using filter parameter.

Uses the Crossref /works endpoint with filter=doi:X,doi:Y,... to fetch
multiple works in a single API call. Supports cursor-based pagination
for large result sets.
"""

import logging
from collections.abc import Sequence
from typing import Any

import httpx

from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services.doi_client.errors import DOINotFoundError, map_to_doi_error
from coda.domain.publication.links import Doi

from ._fetch_publication import CROSSREF_API_BASE, _parse_crossref_response

logger = logging.getLogger(__name__)


def fetch_publications_batch(
    dois: Sequence[Doi],
    timeout: int = 30,
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

    filter_value = ",".join(f"doi:{doi}" for doi in dois)
    params: dict[str, str | int] = {
        "filter": filter_value,
        "rows": len(dois),
        "cursor": "*",
    }

    all_items: list[dict[str, Any]] = []
    max_pages = 10  # Safety limit to prevent infinite pagination
    for _ in range(max_pages):
        try:
            response = httpx.get(
                CROSSREF_API_BASE,
                params=params,
                timeout=timeout,
                follow_redirects=True,
            ).raise_for_status()
            data = response.json()
        except Exception as e:
            return {str(doi): map_to_doi_error(e, doi) for doi in dois}

        message = data.get("message", {})
        items = message.get("items", [])
        if not items:
            break
        all_items.extend(items)

        next_cursor = message.get("next-cursor")
        if not next_cursor:
            break
        params["cursor"] = next_cursor

    # Parse found items into a dict keyed by DOI
    found: dict[str, ExternalPublicationMetadata] = {}
    for item in all_items:
        doi_str = item.get("DOI", "")
        if doi_str:
            try:
                found[doi_str] = _parse_crossref_response({"message": item})
            except Exception as e:
                logger.warning("Failed to parse Crossref item for DOI %s: %s", doi_str, e)

    # Build result for all requested DOIs
    results: dict[str, ExternalPublicationMetadata | Exception] = {}
    for doi in dois:
        doi_str = str(doi)
        if doi_str in found:
            results[doi_str] = found[doi_str]
        elif doi_str not in results:
            results[doi_str] = DOINotFoundError(doi)

    return results

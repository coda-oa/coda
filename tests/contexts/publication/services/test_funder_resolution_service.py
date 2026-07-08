"""Tests for FunderResolutionService.

Tests the ROR-based funder name resolution service in isolation,
using FakeHttpGet to simulate the ROR API.
"""

from typing import Any

import httpx

from coda.contexts.publication.services.funder_resolution_service import FunderResolutionService


class FakeHttpGet:
    """Satisfies HttpGetClient protocol. Returns pre-configured response."""

    def __init__(self, status: int = 200, json_data: dict | None = None) -> None:
        self._status = status
        self._json_data = json_data or {}
        self.last_url: str | None = None
        self.last_params: dict[str, Any] | None = None

    def get(self, url: str, *, params: Any, timeout: int, follow_redirects: bool) -> Any:
        from httpx import Request

        self.last_url = url
        self.last_params = params
        response = httpx.Response(self._status, json=self._json_data, request=Request("GET", url))
        if self._status >= 400:
            from httpx import HTTPStatusError

            raise HTTPStatusError(
                f"HTTP error {self._status}",
                request=Request("GET", url),
                response=response,
            )
        return response


SINGLE_RESPONSE: dict[str, Any] = {
    "number_of_results": 1,
    "items": [
        {
            "id": "https://ror.org/01pp8nd67",
            "names": [
                {"lang": None, "types": ["acronym"], "value": "SI"},
                {"lang": "en", "types": ["alias"], "value": "Smithsonian"},
                {
                    "lang": "en",
                    "types": ["ror_display", "label"],
                    "value": "Smithsonian Institution",
                },
            ],
            "external_ids": [
                {"type": "fundref", "all": ["100000014"], "preferred": None},
            ],
        }
    ],
}

TWO_RESPONSE: dict[str, Any] = {
    "number_of_results": 2,
    "items": [
        {
            "id": "https://ror.org/01pp8nd67",
            "names": [
                {
                    "lang": "en",
                    "types": ["ror_display", "label"],
                    "value": "Smithsonian Institution",
                },
            ],
            "external_ids": [
                {"type": "fundref", "all": ["100000014"], "preferred": None},
            ],
        },
        {
            "id": "https://ror.org/04aj4c181",
            "names": [
                {
                    "lang": "en",
                    "types": ["ror_display", "label"],
                    "value": "Bundesministerium für Bildung und Forschung",
                },
            ],
            "external_ids": [
                {"type": "fundref", "all": ["501100002347"], "preferred": None},
            ],
        },
    ],
}

EMPTY_RESPONSE: dict[str, Any] = {"number_of_results": 0, "items": []}


def test__empty_ids__returns_empty() -> None:
    """Given an empty set of IDs, returns empty dict."""
    fake = FakeHttpGet(status=200, json_data=EMPTY_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    result = sut.resolve_funders(set())
    assert result == {}


def test__single_known_id__returns_name() -> None:
    """A single known Crossref ID returns the resolved name."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    result = sut.resolve_funders({"100000014"})
    assert result == {"100000014": "Smithsonian Institution"}


def test__multiple_known_ids__returns_all() -> None:
    """Multiple known IDs all return their resolved names."""
    fake = FakeHttpGet(status=200, json_data=TWO_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    result = sut.resolve_funders({"100000014", "501100002347"})
    assert result["100000014"] == "Smithsonian Institution"
    assert result["501100002347"] == "Bundesministerium für Bildung und Forschung"


def test__unknown_id__not_in_result() -> None:
    """An ID not found by ROR is excluded from results."""
    fake = FakeHttpGet(status=200, json_data=EMPTY_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    result = sut.resolve_funders({"999999999"})
    assert result == {}


def test__mixed_known_unknown__returns_only_known() -> None:
    """Known IDs are returned, unknown IDs are excluded."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    result = sut.resolve_funders({"100000014", "999999999"})
    assert result == {"100000014": "Smithsonian Institution"}


def test__cached_ids__not_queried_again() -> None:
    """Resolved IDs are cached; second call doesn't query API."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    result1 = sut.resolve_funders({"100000014"})
    assert result1 == {"100000014": "Smithsonian Institution"}
    assert fake.last_params is not None

    # Second call with same ID should use cache, not query
    fake.last_params = None
    result2 = sut.resolve_funders({"100000014"})
    assert result2 == {"100000014": "Smithsonian Institution"}
    assert fake.last_params is None, "Expected cached result, not API query"


def test__partial_cache__only_misses_queried() -> None:
    """When some IDs are cached, only uncached IDs are queried."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    from coda.contexts.publication.services.doi_client._ror import RORClient

    sut = FunderResolutionService(ror_client=RORClient(http_client=fake))
    # First call resolves "100000014"
    sut.resolve_funders({"100000014"})

    # Second call adds a new ID; only the new one should be queried
    fake.last_params = None
    result = sut.resolve_funders({"100000014", "999999999"})
    assert result == {"100000014": "Smithsonian Institution"}
    # The query should still happen (the new ID might match something)
    # but the cached ID shouldn't be re-queried
    if fake.last_params:
        query = fake.last_params.get("query", "")
        assert "100000014" not in query, "Cached ID should not appear in query"

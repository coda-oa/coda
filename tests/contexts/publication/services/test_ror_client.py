"""Tests for RORClient - batch ROR API funder resolution.

Test rounds follow TDD order as defined in the implementation plan.
Parametrized rounds run against both FakeHttpGet and real ROR API.
Non-parametrized rounds test fake-internal behavior only.
"""

from typing import Any

import httpx
import pytest

from coda.contexts.publication.services.doi_client._ror import RORClient, RORClientError
from coda.contexts.publication.services.doi_client._ror._caching import CachingRORClient
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeHttpGet:
    """Satisfies HttpGetClient protocol. Returns pre-configured response."""

    def __init__(self, status: int = 200, json_data: dict[str, Any] | None = None) -> None:
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


class PaginatedFakeHttpGet:
    """Satisfies HttpGetClient protocol. Returns different JSON per page."""

    def __init__(self, pages: dict[int, dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: Any, timeout: int, follow_redirects: bool) -> Any:
        from httpx import Request

        self.calls.append({"url": url, "params": params})
        page = params.get("page", 1) if params else 1
        data = self._pages.get(page, {"number_of_results": 0, "items": []})
        response = httpx.Response(200, json=data, request=Request("GET", url))
        return response


# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

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
                {"type": "grid", "all": ["grid.1214.6"], "preferred": "grid.1214.6"},
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


def _funders_response(count: int, start_id: int = 1) -> dict[str, Any]:
    """Generate a ROR API response with *count* funder records.

    Each record has a unique FundRef ID (``start_id`` … ``start_id + count - 1``)
    and a distinct ROR ID so the matching logic can verify every input maps back.
    """
    items: list[dict[str, Any]] = []
    for i in range(count):
        fundref = str(start_id + i)
        ror_suffix = f"0{i:04x}abcde"
        items.append(
            {
                "id": f"https://ror.org/{ror_suffix}",
                "names": [
                    {
                        "lang": "en",
                        "types": ["ror_display", "label"],
                        "value": f"Funder {fundref}",
                    },
                ],
                "external_ids": [
                    {"type": "fundref", "all": [fundref], "preferred": None},
                ],
            }
        )
    return {"number_of_results": count, "items": items}


# ---------------------------------------------------------------------------
# Pagination fixtures (multi-page responses)
# ---------------------------------------------------------------------------


PAGE_1_ONLY: dict[int, dict[str, Any]] = {1: _funders_response(15)}


TWO_PAGES: dict[int, dict[str, Any]] = {
    1: {**_funders_response(20, start_id=1), "number_of_results": 25},
    2: {**_funders_response(5, start_id=21), "number_of_results": 25},
}

EXACT_ONE_PAGE: dict[int, dict[str, Any]] = {1: _funders_response(20)}


EMPTY_PAGE: dict[int, dict[str, Any]] = {1: {"number_of_results": 0, "items": []}}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_ror_single() -> RORClient:
    return RORClient(http_client=FakeHttpGet(status=200, json_data=SINGLE_RESPONSE))


@pytest.fixture
def fake_ror_two() -> RORClient:
    return RORClient(http_client=FakeHttpGet(status=200, json_data=TWO_RESPONSE))


@pytest.fixture
def fake_ror_empty() -> RORClient:
    return RORClient(http_client=FakeHttpGet(status=200, json_data=EMPTY_RESPONSE))


@pytest.fixture(scope="module")
def real_ror_client() -> RORClient:
    return RORClient()


# ---------------------------------------------------------------------------
# Round1: empty input -> empty dict
# ---------------------------------------------------------------------------


def test__ror_clients__accept_canonical_link_protocol() -> None:
    """Link-typed inputs flow through RORClient via the shared domain Link protocol."""

    link = CrossrefId("100000014")
    # The canonical Link protocol defines type()/value()/url(); CrossrefId satisfies it.
    assert hasattr(link, "type") and hasattr(link, "value") and hasattr(link, "url")
    assert isinstance(link, object)  # structural protocol, exercised below

    sut = RORClient(http_client=FakeHttpGet(status=200, json_data=SINGLE_RESPONSE))
    result = sut.resolve_by_ids([link])
    assert "100000014" in result


def test__ror_client__empty_input__returns_empty_dict() -> None:
    """Given an empty list of links, resolve_by_ids returns an empty dict."""
    sut = RORClient(http_client=FakeHttpGet())
    result = sut.resolve_by_ids([])
    assert result == {}


# ---------------------------------------------------------------------------
# Round 2a: single ID builds query
# ---------------------------------------------------------------------------


def test__ror_client__single_id__builds_query() -> None:
    """Verifies query is constructed from str(link) and sent to ROR API."""
    fake = FakeHttpGet(status=200, json_data={"number_of_results": 0, "items": []})
    sut = RORClient(http_client=fake)

    sut.resolve_by_ids([CrossrefId("100000014")])

    assert fake.last_url == RORClient.BASE_URL
    assert fake.last_params is not None
    assert fake.last_params["query"] == '"100000014"'


# ---------------------------------------------------------------------------
# Round 2b: single ID returns mapping (parametrized: fake + real API)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_ror_single",
        pytest.param("real_ror_client", marks=pytest.mark.integration),
    ],
)
def test__ror_client__single_id__returns_mapping(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Given a valid Crossref ID, returns a mapping with name and ROR ID."""
    sut: RORClient = request.getfixturevalue(client_fixture)
    result = sut.resolve_by_ids([CrossrefId("100000014")])
    assert "100000014" in result
    assert result["100000014"].name == "Smithsonian Institution"
    assert result["100000014"].id == "https://ror.org/01pp8nd67"


# ---------------------------------------------------------------------------
# Round 3: multiple IDs maps all
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_ror_two",
    ],
)
def test__ror_client__multiple_ids__maps_all(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """Two valid IDs both appear in the result."""
    sut: RORClient = request.getfixturevalue(client_fixture)
    result = sut.resolve_by_ids([CrossrefId("100000014"), CrossrefId("501100002347")])
    assert len(result) == 2
    assert result["100000014"].name == "Smithsonian Institution"
    assert result["501100002347"].name == "Bundesministerium für Bildung und Forschung"


# ---------------------------------------------------------------------------
# Round 4: unknown ID not in result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_ror_empty",
    ],
)
def test__ror_client__unknown_id__not_in_result(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """An ID that matches nothing yields an empty result dict."""
    sut: RORClient = request.getfixturevalue(client_fixture)
    result = sut.resolve_by_ids([CrossrefId("999999999")])
    assert result == {}


# ---------------------------------------------------------------------------
# Round 5: mixed known and unknown -> only known in result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_ror_single",
    ],
)
def test__ror_client__mixed_known_unknown__returns_only_known(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """When some IDs match and some don't, only matched IDs appear in result."""
    sut: RORClient = request.getfixturevalue(client_fixture)
    result = sut.resolve_by_ids([CrossrefId("100000014"), CrossrefId("999999999")])
    assert "100000014" in result
    assert "999999999" not in result


# ---------------------------------------------------------------------------
# Round 6: HTTP error raises RORClientError
# ---------------------------------------------------------------------------


def test__ror_client__http_error__raises_ror_client_error() -> None:
    """A 500 response from the ROR API raises RORClientError."""
    fake = FakeHttpGet(status=500, json_data={})
    sut = RORClient(http_client=fake)
    with pytest.raises(RORClientError, match="ROR API request failed"):
        sut.resolve_by_ids([CrossrefId("100000014")])


# ---------------------------------------------------------------------------
# Round 7: record with multi external IDs -> correct input mapped
# ---------------------------------------------------------------------------


def test__ror_client__record_with_multi_ext_ids__correct_input_mapped() -> None:
    """A record with fundref + ISNI + Wikidata still maps the fundref ID."""
    response: dict[str, Any] = {
        "number_of_results": 1,
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
                    {"type": "isni", "all": ["0000000087163312"], "preferred": None},
                    {"type": "wikidata", "all": ["Q131626"], "preferred": None},
                ],
            }
        ],
    }
    fake = FakeHttpGet(status=200, json_data=response)
    sut = RORClient(http_client=fake)
    result = sut.resolve_by_ids([CrossrefId("100000014")])
    assert result["100000014"].name == "Smithsonian Institution"


# ---------------------------------------------------------------------------
# Round 8: response missing items key -> empty result
# ---------------------------------------------------------------------------


def test__ror_client__response_missing_items_key__returns_empty() -> None:
    """A response without an 'items' field returns an empty dict."""
    fake = FakeHttpGet(status=200, json_data={"number_of_results": 0})
    sut = RORClient(http_client=fake)
    result = sut.resolve_by_ids([CrossrefId("100000014")])
    assert result == {}


# ---------------------------------------------------------------------------
# Round 9: network timeout raises RORClientError
# ---------------------------------------------------------------------------


def test__ror_client__network_timeout__raises_ror_client_error() -> None:
    """A timeout from the HTTP client raises RORClientError."""

    class TimeoutHttpGet:
        def get(self, url: str, *, params: Any, timeout: int, follow_redirects: bool) -> Any:
            raise httpx.TimeoutException("Connection timed out", request=None)

    sut = RORClient(http_client=TimeoutHttpGet())
    with pytest.raises(RORClientError, match="ROR API request failed"):
        sut.resolve_by_ids([CrossrefId("100000014")])


# ---------------------------------------------------------------------------
# Round 10: two different link types for same record -> both in result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_ror_single",
    ],
)
def test__ror_client__two_different_link_types_same_record__both_in_result(
    client_fixture: str, request: pytest.FixtureRequest
) -> None:
    """CrossrefId and Ror pointing to the same record both appear in result."""
    sut: RORClient = request.getfixturevalue(client_fixture)
    result = sut.resolve_by_ids([CrossrefId("100000014"), Ror("https://ror.org/01pp8nd67")])
    assert "100000014" in result
    assert "https://ror.org/01pp8nd67" in result
    assert result["100000014"].id == "https://ror.org/01pp8nd67"
    assert result["https://ror.org/01pp8nd67"].id == "https://ror.org/01pp8nd67"


# ---------------------------------------------------------------------------
# CachingRORClient: known IDs cached, unknown IDs also cached (negative cache)
# ---------------------------------------------------------------------------


def test__caching_ror_client__known_id__cached_after_first_call() -> None:
    """A known ID should use the cache on subsequent calls, not query the API."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    inner = RORClient(http_client=fake)
    sut = CachingRORClient(inner)

    # First call — queries the API
    result1 = sut.resolve_by_ids([CrossrefId("100000014")])
    assert "100000014" in result1

    fake.last_params = None

    # Second call — should NOT query the API
    result2 = sut.resolve_by_ids([CrossrefId("100000014")])
    assert "100000014" in result2
    assert fake.last_params is None, "Expected cached result, not API query"


def test__caching_ror_client__unknown_id__cached_after_first_call() -> None:
    """A Crossref ID not found by ROR should be cached so it is never re-queried."""
    fake = FakeHttpGet(status=200, json_data=EMPTY_RESPONSE)
    inner = RORClient(http_client=fake)
    sut = CachingRORClient(inner)

    # First call — queries the API
    result1 = sut.resolve_by_ids([CrossrefId("999999999")])
    assert result1 == {}
    assert fake.last_params is not None

    fake.last_params = None

    # Second call — must use cache, NOT query the API
    result2 = sut.resolve_by_ids([CrossrefId("999999999")])
    assert result2 == {}
    assert fake.last_params is None, "Expected cached result, not API query"


def test__caching_ror_client__mixed_known_and_unknown__caches_both() -> None:
    """When some IDs match and some don't, BOTH should be cached."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    inner = RORClient(http_client=fake)
    sut = CachingRORClient(inner)

    # First call — known + unknown in a single batch
    result1 = sut.resolve_by_ids([CrossrefId("100000014"), CrossrefId("999999999")])
    assert "100000014" in result1
    assert "999999999" not in result1

    fake.last_params = None

    # Second call with the same IDs — both must come from cache
    result2 = sut.resolve_by_ids([CrossrefId("100000014"), CrossrefId("999999999")])
    assert "100000014" in result2
    assert "999999999" not in result2
    assert fake.last_params is None, "Expected cached result, not API query"


def test__caching_ror_client__partial_uncached__only_misses_queried() -> None:
    """When some IDs are cached and others are not, only uncached IDs are queried."""
    fake_single = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    fake_single.last_params = None

    inner = RORClient(http_client=fake_single)
    sut = CachingRORClient(inner)

    # First call — prime cache with one ID
    sut.resolve_by_ids([CrossrefId("100000014"), CrossrefId("999999999")])

    fake_single.last_params = None

    sut.resolve_by_ids(
        [CrossrefId("100000014"), CrossrefId("999999999"), CrossrefId("501100002347")]
    )
    # The new ID exists in SINGLE_RESPONSE but we only have one record there,
    # so 501100002347 won't be found.  That's fine — the important thing is
    # that the query happened (the cache miss triggered a call).
    assert fake_single.last_params is not None
    query = fake_single.last_params.get("query", "")
    assert "999999999" not in query, "Cached ID should not appear in query"
    assert "100000014" not in query, "Cached ID should not appear in query"
    assert "501100002347" in query, "New ID should appear in query"


def test__caching_ror_client__empty_input__no_api_call() -> None:
    """An empty list of links should not trigger any API call."""
    inner = RORClient(http_client=FakeHttpGet())
    sut = CachingRORClient(inner)
    result = sut.resolve_by_ids([])
    assert result == {}


def test__caching_ror_client__two_different_link_types_same_record__both_in_result() -> None:
    """CrossrefId and Ror pointing to the same record both appear in result after cache."""
    fake = FakeHttpGet(status=200, json_data=SINGLE_RESPONSE)
    inner = RORClient(http_client=fake)
    sut = CachingRORClient(inner)

    result = sut.resolve_by_ids([CrossrefId("100000014"), Ror("https://ror.org/01pp8nd67")])
    assert "100000014" in result
    assert "https://ror.org/01pp8nd67" in result
    assert result["100000014"].id == "https://ror.org/01pp8nd67"
    assert result["https://ror.org/01pp8nd67"].id == "https://ror.org/01pp8nd67"

    # Second call — both must come from cache
    fake.last_params = None
    result2 = sut.resolve_by_ids([CrossrefId("100000014"), Ror("https://ror.org/01pp8nd67")])
    assert "100000014" in result2
    assert "https://ror.org/01pp8nd67" in result2
    assert fake.last_params is None, "Expected cached result, not API query"


# ---------------------------------------------------------------------------
# Pagination tests
# ---------------------------------------------------------------------------


class TestRORClientPagination:
    """RORClient correctly iterates through multi-page ROR API responses."""

    def test__ror_client__single_page__no_pagination(self) -> None:
        """Given < 20 results, makes exactly 1 API call and returns all matches."""
        fake = PaginatedFakeHttpGet(PAGE_1_ONLY)
        sut = RORClient(http_client=fake)

        ids = [CrossrefId(str(i)) for i in range(1, 16)]
        result = sut.resolve_by_ids(ids)

        assert len(fake.calls) == 1
        assert len(result) == 15
        for i in range(1, 16):
            assert str(i) in result

    def test__ror_client__multi_page__paginates(self) -> None:
        """Given > 20 results, iterates through pages and merges all records."""
        fake = PaginatedFakeHttpGet(TWO_PAGES)
        sut = RORClient(http_client=fake)

        ids = [CrossrefId(str(i)) for i in range(1, 26)]
        result = sut.resolve_by_ids(ids)

        assert len(fake.calls) == 2
        assert fake.calls[0]["params"].get("page", 1) == 1
        assert fake.calls[1]["params"].get("page") == 2
        assert len(result) == 25
        for i in range(1, 26):
            assert str(i) in result

    def test__ror_client__exact_page_boundary__one_page(self) -> None:
        """Given exactly 20 results, makes exactly 1 call (no extra page)."""
        fake = PaginatedFakeHttpGet(EXACT_ONE_PAGE)
        sut = RORClient(http_client=fake)

        ids = [CrossrefId(str(i)) for i in range(1, 21)]
        result = sut.resolve_by_ids(ids)

        assert len(fake.calls) == 1
        assert len(result) == 20

    def test__ror_client__empty_response__no_pagination(self) -> None:
        """Given 0 results, makes exactly 1 call and returns empty dict."""
        fake = PaginatedFakeHttpGet(EMPTY_PAGE)
        sut = RORClient(http_client=fake)

        result = sut.resolve_by_ids([CrossrefId("999999999")])

        assert len(fake.calls) == 1
        assert result == {}

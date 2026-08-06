"""Tests for Crossref batch fetch pagination logic.

Seam: crossref.fetch_publications_batch() — public function
Test double: FakeHttpxClient + FakeHttpxResponse injected via the http_client parameter
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coda.contexts.fundingrequest.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.fundingrequest.services.doi_import.doi_client import crossref
from coda.contexts.fundingrequest.services.doi_import.doi_client.errors import DOINotFoundError
from coda.domain.publication.links import Doi


class FakeHttpxResponse:
    """Simulates an httpx.Response for test purposes.

    Satisfies the .raise_for_status().json() chain used by fetch_publications_batch.
    """

    def __init__(self, items: list[dict[str, Any]], next_cursor: str | None = None) -> None:
        self._items = items
        self._next_cursor = next_cursor

    def raise_for_status(self) -> "FakeHttpxResponse":
        return self

    def json(self) -> dict[str, Any]:
        return {
            "message": {
                "items": self._items,
                "next-cursor": self._next_cursor,
            }
        }


class FakeHttpxClient:
    """Fake HTTP client that returns pre-configured responses or raises errors.

    Satisfies the HttpGetClient protocol expected by fetch_publications_batch.

    When constructed with a single response, that response is returned on every
    call (useful for single-page scenarios). When constructed with multiple
    items, they are consumed from the sequence one at a time.
    """

    def __init__(self, *items: FakeHttpxResponse | BaseException) -> None:
        self._sequence: list[FakeHttpxResponse | BaseException] = list(items)
        self.get_call_count = 0

    def get(self, url: str, **kwargs: Any) -> FakeHttpxResponse:
        self.get_call_count += 1
        if not self._sequence:
            return FakeHttpxResponse([])

        item = self._sequence[0]
        if isinstance(item, BaseException):
            raise item

        if len(self._sequence) == 1:
            return item  # Single item: return it every time

        self._sequence.pop(0)
        return item


def _make_item(doi: str, title: str = "Test Title") -> dict[str, Any]:
    """A minimal Crossref item that _parse_crossref_response can process."""
    return {
        "DOI": doi,
        "title": [title],
        "type": "journal-article",
        "publisher": "Test Publisher",
        "author": [],
    }


def assert_all_found(result: Mapping[str, object], dois: list[Doi]) -> None:
    """Every requested DOI resolved to ExternalPublicationMetadata, not an error."""
    for doi in dois:
        assert isinstance(
            result[str(doi)], ExternalPublicationMetadata
        ), f"{doi} should be metadata"


def assert_not_found(result: Mapping[str, object], dois: list[Doi]) -> None:
    """Every requested DOI received a DOINotFoundError."""
    for doi in dois:
        assert isinstance(result[str(doi)], DOINotFoundError), f"{doi} should be not-found"


def assert_pages_requested(client: FakeHttpxClient, count: int) -> None:
    """Verify the batch fetch paginated through exactly the expected number of pages."""
    assert client.get_call_count == count


class TestCrossrefBatchPagination:
    """Tests for the cursor-based pagination loop in fetch_publications_batch."""

    def test__fetch_publications_batch__single_page_fewer_items_than_rows__one_http_call(
        self,
    ) -> None:
        """Given response with fewer items than rows, only one HTTP request is made."""
        dois = [Doi(f"10.1234/paginate.{i}") for i in range(5)]
        items = [_make_item(str(d)) for d in dois[:3]]

        fake_client = FakeHttpxClient(FakeHttpxResponse(items))
        result = crossref.fetch_publications_batch(dois, http_client=fake_client)

        assert_pages_requested(fake_client, 1)
        assert_all_found(result, dois[:3])
        assert_not_found(result, dois[3:])

    def test__fetch_publications_batch__single_page_all_found__returns_metadata(self) -> None:
        """Given all DOIs found in one page, returns metadata (not errors) for all."""
        dois = [Doi(f"10.1234/found.{i}") for i in range(3)]
        items = [_make_item(str(d), title=f"Title {i}") for i, d in enumerate(dois)]

        fake_client = FakeHttpxClient(FakeHttpxResponse(items))
        result = crossref.fetch_publications_batch(dois, http_client=fake_client)

        assert_all_found(result, dois)

    def test__fetch_publications_batch__single_page_some_not_found__returns_mixed(self) -> None:
        """Given some DOIs missing from response, missing ones get DOINotFoundError."""
        dois = [Doi("10.1234/found"), Doi("10.1234/missing")]
        items = [_make_item("10.1234/found")]

        fake_client = FakeHttpxClient(FakeHttpxResponse(items))
        result = crossref.fetch_publications_batch(dois, http_client=fake_client)

        assert_all_found(result, [Doi("10.1234/found")])
        assert_not_found(result, [Doi("10.1234/missing")])

    def test__fetch_publications_batch__single_page_empty_response__returns_not_found_for_all(
        self,
    ) -> None:
        """Given an empty items list, all DOIs get DOINotFoundError."""
        dois = [Doi("10.1234/empty.a"), Doi("10.1234/empty.b")]

        fake_client = FakeHttpxClient(FakeHttpxResponse([]))
        result = crossref.fetch_publications_batch(dois, http_client=fake_client)

        assert_pages_requested(fake_client, 1)
        assert_not_found(result, dois)

    def test__fetch_publications_batch__two_pages_aggregates_items_from_both(self) -> None:
        """Given a next-cursor and a second page, items from both pages are returned."""
        dois = [Doi(f"10.1234/page1.{i}") for i in range(3)]
        page1_items = [_make_item(str(d)) for d in dois]
        page2_items = [_make_item("10.1234/page2.extra")]

        fake_client = FakeHttpxClient(
            FakeHttpxResponse(page1_items, next_cursor="cursor-2"),
            FakeHttpxResponse(page2_items),
        )
        result = crossref.fetch_publications_batch(
            dois + [Doi("10.1234/page2.extra")], http_client=fake_client
        )

        assert_pages_requested(fake_client, 2)
        assert_all_found(result, dois + [Doi("10.1234/page2.extra")])

    def test__fetch_publications_batch__first_page_equals_rows__continues_to_next_page(
        self,
    ) -> None:
        """Given first page returns == rows items with next-cursor, makes a second call."""
        dois = [Doi(f"10.1234/paginate.{i}") for i in range(3)]
        page1_items = [_make_item(str(d)) for d in dois]
        page2_items = [_make_item("10.1234/extra")]

        fake_client = FakeHttpxClient(
            FakeHttpxResponse(page1_items, next_cursor="cursor-next"),
            FakeHttpxResponse(page2_items),
        )
        result = crossref.fetch_publications_batch(
            dois + [Doi("10.1234/extra")], http_client=fake_client
        )

        assert_pages_requested(fake_client, 2)
        assert_all_found(result, dois + [Doi("10.1234/extra")])

    def test__fetch_publications_batch__http_error__returns_errors_for_all_dois(self) -> None:
        """Given an HTTP error on the first request, all DOIs get error results."""
        dois = [Doi("10.1234/error.a"), Doi("10.1234/error.b")]

        fake_client = FakeHttpxClient(RuntimeError("Connection failed"))
        result = crossref.fetch_publications_batch(dois, http_client=fake_client)

        assert_pages_requested(fake_client, 1)
        for doi in dois:
            assert isinstance(result[str(doi)], Exception), f"{doi} should be an error"

    def test__fetch_publications_batch__http_error_on_second_page__keeps_first_page_results(
        self,
    ) -> None:
        """Given first page succeeds but second page fails, first-page results are kept."""
        dois = [Doi(f"10.1234/paginate.{i}") for i in range(3)]
        page1_items = [_make_item(str(d)) for d in dois]

        fake_client = FakeHttpxClient(
            FakeHttpxResponse(page1_items, next_cursor="cursor-next"),
            RuntimeError("Connection failed on page 2"),
        )
        result = crossref.fetch_publications_batch(
            dois + [Doi("10.1234/extra")], http_client=fake_client
        )

        assert_pages_requested(fake_client, 2)
        assert_all_found(result, dois)
        assert isinstance(result["10.1234/extra"], Exception)


class TestCrossrefBatchWithRealData:
    """Tests using a real Crossref response recorded as a fixture."""

    _FIXTURE_PATH = Path(__file__).parent / "fixtures" / "crossref_batch_100_response.json"

    def test__fetch_publications_batch__real_100_dois__parses_all_successfully(self) -> None:
        """Given a real Crossref response for 100 DOIs, all are parsed into metadata."""
        with open(self._FIXTURE_PATH) as f:
            fixture = json.load(f)

        msg = fixture["message"]
        all_items = msg["items"]
        dois = [Doi(item["DOI"]) for item in all_items]

        fake_client = FakeHttpxClient(
            FakeHttpxResponse(all_items, next_cursor=msg.get("next-cursor")),
            FakeHttpxResponse([]),
        )
        result = crossref.fetch_publications_batch(dois, http_client=fake_client)

        assert_pages_requested(fake_client, 2)
        assert len(result) == 100
        assert_all_found(result, dois)

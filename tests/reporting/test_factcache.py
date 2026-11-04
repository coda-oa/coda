"""The statistics fact cache: hits skip the fact pipeline, writes invalidate.

The behavioral contract: the first request for a filter set runs the fact
pipeline (the fact-graph queries fire); a second identical request performs
none (the cached tuple answers); any write to a fact-relevant model
invalidates, so the next request runs the pipeline again. Display state
(tab, compare, resolution) must not widen the key — switching tabs reuses
the same fact set."""

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.reporting import factcache
from tests.reporting.test_page import seed


def _region_url(client: Client, **query: str) -> None:
    client.get(
        reverse("reporting:stats_fundingrequests_region"),
        data={"start_date": "2026-01-01", "end_date": "2026-12-31", **query},
        headers={"hx-request": "true"},
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fact_cache__second_identical_request__skips_the_fact_pipeline(
    client: Client,
) -> None:
    seed()
    miss_queries = _fact_fetch_count(client)  # miss: runs the pipeline, caches
    hit_queries = _fact_fetch_count(client)  # hit: the cached tuple answers
    assert miss_queries > 0
    assert hit_queries == 0


def _fact_fetch_count(client: Client) -> int:
    """The fact pipeline's own queries of one more region request: the
    DISTINCT funding-request fetch plus its prefetch graph. Form choice
    lists and the treemap's hierarchy query are not part of the pipeline
    and stay uncached, so they must not count."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        _region_url(client)
    return sum(
        1
        for q in ctx.captured_queries
        if "DISTINCT" in q["sql"] and "fundingrequests_fundingrequest" in q["sql"]
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fact_cache__write_invalidates(client: Client) -> None:
    fixture = seed()
    assert _fact_fetch_count(client) > 0  # miss: pipeline runs
    assert _fact_fetch_count(client) == 0  # cached

    fixture.funded.external_funding.first().save()  # any fact-relevant write

    assert factcache.generation() > 0
    assert _fact_fetch_count(client) > 0  # invalidated: pipeline runs again


@pytest.mark.django_db
def test__fact_cache__display_state_does_not_widen_the_key(client: Client) -> None:
    seed()
    params: dict[str, str] = {}
    key_plain = factcache.facts_key(_querydict(params), currency=_currency())
    key_tab = factcache.facts_key(
        _querydict({"tab": "venues", "resolution": "monthly"}), currency=_currency()
    )
    assert key_plain == key_tab


@pytest.mark.django_db
def test__fact_cache__different_filters__different_keys(client: Client) -> None:
    seed()
    key_a = factcache.facts_key(_querydict({"search_term": "a"}), currency=_currency())
    key_b = factcache.facts_key(_querydict({"search_term": "b"}), currency=_currency())
    assert key_a != key_b


@pytest.mark.django_db
def test__fact_cache__comparison_period_enters_the_key(client: Client) -> None:
    seed()
    from coda.domain.date import DateRange

    params = _querydict({"start_date": "2026-01-01", "end_date": "2026-12-31"})
    currency = _currency()
    key_current = factcache.facts_key(params, currency)
    key_compared = factcache.facts_key(
        params,
        currency,
        comparison_period=DateRange(_d(2025, 1, 1), _d(2025, 12, 31)),
    )
    assert key_current != key_compared


def _d(year: int, month: int, day: int) -> object:
    import datetime

    return datetime.date(year, month, day)


def _querydict(data: dict[str, str]) -> object:
    from django.http import QueryDict

    q = QueryDict(mutable=True)
    for k, v in data.items():
        q[k] = v
    return q


def _currency() -> object:
    from coda.apps.preferences.models import GlobalPreferences

    return GlobalPreferences.get_home_currency()

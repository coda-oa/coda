"""Cache for the statistics fact set (plan §4).

The facts pipeline — filtered ORM fetch plus per-request money conversion —
is the dominant cost of every statistics region request (2.4–3.5s on dev
data), and it is tab-independent: every tab switch and every filter edit
recomputes it. The fact tuple depends only on the filter params, the home
currency and the data, so it caches cleanly.

The cache is the process's default Django cache (``settings.CACHES``).
Entries are pickled, so every hit returns a fresh copy of the fact tuple;
sharing is safe even though ``RequestFact`` is only shallowly immutable
(its Mapping fields are plain dicts), and the pure layer only reads facts
anyway (``aggregation``, ``charts`` and ``timeline`` iterate the mappings,
never assign into them). How many processes share this cache is a
deployment choice: more processes mean more independent caches, each still
correct, just colder at startup.

Entries are keyed by the page's own filter params (display state — tab,
compare params, resolution, page — is excluded, matching the list URLs),
the home currency, and the resolved comparison period where one is
fetched. A data-generation counter invalidates on every write to any
model the fetch graph reads; the TTL bounds staleness if a write path ever
escapes the receivers. The default LocMemCache has no LRU: distinct filter
combinations accumulate until their TTL expires, bounded by the 24h TTL.
"""

import datetime
import hashlib
from collections.abc import Callable

from django.core.cache import cache
from django.http import QueryDict

from coda.contexts.statistics.dto import RequestFact
from coda.domain.date import DateRange
from coda.domain.money import Currency

GENERATION_KEY = "statistics_facts_generation"
FACTS_TTL = int(datetime.timedelta(hours=24).total_seconds())
"""Bounds staleness if a write path escapes the receivers (bulk ops bypass
post_save/post_delete); invalidation itself is the generation counter, which
the signal receivers bump on every ordinary write."""

#: The statistics page's own state: not filters, so it must not widen the
#: facts cache key here, and drilldown keeps it out of the list URLs it
#: derives from the page.
DISPLAY_STATE_PARAMS = (
    "page",
    "tab",
    "compare",
    "compare_start_date",
    "compare_end_date",
    "resolution",
)


def generation() -> int:
    """The data generation: bumped on every write to a fact-relevant model."""
    gen = cache.get(GENERATION_KEY, 0)
    return gen if isinstance(gen, int) else 0


def bump_generation() -> None:
    """Invalidate every cached fact set. Called from post_save/post_delete
    receivers over the fetch graph's model set."""
    # add() first: two threads racing on an absent key must not both fall
    # into the set() fallback and collapse two bumps into one generation.
    if not cache.add(GENERATION_KEY, 1, None):
        cache.incr(GENERATION_KEY)


def facts_key(
    params: QueryDict, currency: Currency, comparison_period: DateRange | None = None
) -> str:
    """The cache key for one fact set: filter params, currency, generation,
    and the comparison period when the set covers it."""
    filter_items = sorted(
        (key, value)
        for key, values in params.lists()
        for value in values
        if key not in DISPLAY_STATE_PARAMS
    )
    material = repr((filter_items, currency.code, comparison_period, generation()))
    digest = hashlib.sha256(material.encode()).hexdigest()
    return f"statistics_facts_{digest}"


def facts_for(
    params: QueryDict,
    currency: Currency,
    build: Callable[[DateRange | None], tuple[RequestFact, ...]],
    *,
    comparison_period: DateRange | None = None,
) -> tuple[RequestFact, ...]:
    """The fact set for the given filter params, cached.

    ``build`` runs the pipeline on a miss; it receives the comparison period
    (None: fetch for the params' own date range) and returns the fact tuple.
    The view builds it once from its own filter form, so the form's choice
    queries are paid per request regardless of a hit or miss — the cache
    covers only the fact pipeline, which is the expensive part.

    A hit returns a fresh copy of the cached tuple; the pure layer treats
    facts as read-only. A miss calls ``build`` and caches the result.
    Entries are pickled, so an entry left by an older code version is not
    detected at read time; a schema change would surface at render time
    instead. No version machinery is spent on that.
    """
    key = facts_key(params, currency, comparison_period)
    facts = cache.get(key)
    if isinstance(facts, tuple):
        return facts
    # Absent, or garbage from an unexpected writer: rebuild.
    facts = build(comparison_period)
    cache.set(key, facts, FACTS_TTL)
    return facts

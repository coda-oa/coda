"""Panter pricemonitor API client.

All documented routes from the pricemonitor API (see ``coda-panter-api.md``)
are implemented here, even though only ``fetch_journal_pricing`` is currently
used by the APC panel view.

Usage::

    from coda.contexts.fundingrequest.services.panter import (
        fetch_journal_pricing,
        journal_info,
    )

    pricing = fetch_journal_pricing("1234-5678")
    if pricing:
        for apc in pricing.article_processing_charges:
            print(apc.fee)
"""

from collections.abc import Sequence
from datetime import date
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache
from pydantic import BaseModel, Field


# ── Response models ─────────────────────────────────────────────


class MonetaryAmount(BaseModel):
    """A numeric price value in a specific currency.

    Corresponds to the ``MonetaryAmount`` type in ``journal-metadata-schema.json``.
    The value is a rounded integer; fractional amounts should be rounded to the
    nearest whole unit of the given currency.
    """

    value: int
    currency: str


class APC(BaseModel):
    """Article Processing Charge for a specific article type or category.

    Mirrors the ``APC`` sub-schema from ``journal-metadata-schema.json``.
    An APC entry may apply to a specific ``article_type`` (e.g. ``"research article"``),
    a ``category`` label, or both. The ``fee`` field lists prices in different
    currencies when the journal publishes its APC in multiple currencies.
    """

    article_type: str | None = None
    category: str | None = None
    per_page: bool = False
    per_figure: bool = False
    license_name: str | None = None
    license_type: str | None = None
    fee: list[MonetaryAmount] = Field(default_factory=list)


class Discount(BaseModel):
    """A waiver or discount on publication fees.

    Mirrors the ``Discount`` sub-schema from ``journal-metadata-schema.json``.

    Three variants exist:
    - ``"waiver"`` — full fee waiver (no amount or percentage set).
    - ``"percent"`` — percentage discount (``percentage`` field).
    - ``"fixed"`` — fixed monetary discount (``amount`` field).

    Eligibility is described as a free-text statement (``eligibility``) and
    categorised by ``eligibility_mechanism`` for machine processing.
    """

    type: str
    amount: MonetaryAmount | None = None
    percentage: float | None = None
    eligibility: str
    eligibility_mechanism: str = "unconditional"
    eligible_article_types: list[str] = Field(default_factory=list)
    time_limited: bool = False
    expires_after: date | None = None


class Pricing(BaseModel):
    """Container for a journal's APC list and discount list.

    Parsed from the ``additional_metadata.pricing`` field returned by the
    ``JournalInfo`` API endpoint. Either or both lists may be empty.
    """

    article_processing_charges: list[APC] = Field(default_factory=list)
    discounts: list[Discount] = Field(default_factory=list)


class JournalInfo(BaseModel):
    """Full journal information returned by the ``JournalInfo`` endpoints.

    The ``additional_metadata`` dict contains the rich journal metadata blob
    (see ``journal-metadata-schema.json``). Call :meth:`pricing` to extract
    the ``Pricing`` sub-object. ``issn`` is the lookup key used in the API
    request; the response may also carry ``pissn``, ``eissn``, and ``lissn``
    when the API has them.
    """

    issn: str
    journal_name: str | None = None
    publisher_id: int | None = None
    publisher_name: str | None = None
    additional_metadata: dict[str, Any] = Field(default_factory=dict)
    pissn: str | None = None
    eissn: str | None = None
    lissn: str | None = None
    date_created: str | None = None
    date_modified: str | None = None

    def pricing(self) -> Pricing | None:
        """Extract the ``Pricing`` sub-object from ``additional_metadata``.

        Returns ``None`` when the ``pricing`` key is absent or when the
        raw value cannot be parsed (e.g. schema mismatch).
        """
        raw = self.additional_metadata.get("pricing")
        if raw is None:
            return None
        try:
            return Pricing.model_validate(raw)
        except Exception:
            return None


class Publisher(BaseModel):
    """A publisher as returned by the ``GET /Publisher`` endpoint."""

    id: int
    name: str


class PublisherJournal(BaseModel):
    """A journal listing inside the ``GET /Publisher/{id}`` response."""

    name: str | None = None
    pissn: str | None = None
    eissn: str | None = None
    lissn: str | None = None


class JournalSearchResult(BaseModel):
    """A single journal result from the ``POST /JournalSearch`` endpoint."""

    journal_id: int
    journal_name: str | None = None
    publisher_id: int | None = None
    publisher_name: str | None = None
    pissn: str | None = None
    eissn: str | None = None
    lissn: str | None = None


# ── HTTP helpers ────────────────────────────────────────────────


def _get(path: str) -> dict[str, Any] | None:
    """Perform a GET request against the Panter API.

    Args:
        path: URL path relative to ``PANTER_API_BASE`` (e.g. ``"/Publisher"``).

    Returns:
        Parsed JSON response body, or ``None`` on any HTTP error
        (connection failure, timeout, non-2xx status) or JSON decode failure.
    """
    url = f"{settings.PANTER_API_BASE}{path}"
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def _post(path: str, body: Any = None) -> dict[str, Any] | None:
    """Perform a POST request against the Panter API.

    Args:
        path: URL path relative to ``PANTER_API_BASE`` (e.g. ``"/JournalInfo"``).
        body: JSON-serialisable request body.

    Returns:
        Parsed JSON response body, or ``None`` on any HTTP error
        (connection failure, timeout, non-2xx status) or JSON decode failure.
    """
    url = f"{settings.PANTER_API_BASE}{path}"
    try:
        resp = httpx.post(url, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


# ── Public API routes ───────────────────────────────────────────


def list_publishers() -> Sequence[Publisher]:
    """Fetch all publishers from the pricemonitor database.

    Corresponds to ``GET /pricemonitor/coda/v1/Publisher``.

    Returns:
        A (possibly empty) sequence of :class:`Publisher` instances.
    """
    data = _get("/Publisher")
    if data is None:
        return []
    return [Publisher.model_validate(p) for p in data.get("publishers", [])]


def publisher_journals(publisher_id: int) -> Sequence[PublisherJournal]:
    """Fetch journals belonging to a specific publisher.

    Corresponds to ``GET /pricemonitor/coda/v1/Publisher/{publisher_id}``.

    Args:
        publisher_id: Internal publisher ID from the pricemonitor database.

    Returns:
        A (possibly empty) sequence of :class:`PublisherJournal` instances.
        Empty rows (no ``journal_name``) are filtered by the API.
    """
    data = _get(f"/Publisher/{publisher_id}")
    if data is None:
        return []
    return [PublisherJournal.model_validate(j) for j in data.get("journals", [])]


# Cache TTL for Panter lookups. APC pricing changes infrequently, so a
# day is a reasonable balance between freshness and avoiding repeated
# synchronous calls to the external API.
PANTER_CACHE_TTL = 60 * 60 * 24

# Sentinel to distinguish "not in cache" from a cached ``None`` result.
_NOT_CACHED = object()


def journal_info(issn: str) -> JournalInfo | None:
    """Fetch journal information for a single ISSN.

    Corresponds to ``GET /pricemonitor/coda/v1/JournalInfo/{issn}``.

    The response is deduplicated server-side by freshness
    (``date_created`` / ``date_modified``), returning the most up-to-date
    row per ISSN. Results are cached in Django's cache backend for
    :data:`PANTER_CACHE_TTL` seconds.

    Args:
        issn: ISSN string in ``NNNN-NNNN`` form (pissn, eissn, or lissn).

    Returns:
        :class:`JournalInfo` if the ISSN is found, ``None`` otherwise
        (unknown ISSN, API unreachable, or empty response).
    """
    key = f"panter:journal_info:{issn}"
    cached = cache.get(key, _NOT_CACHED)
    if cached is not _NOT_CACHED:
        return cached
    data = _get(f"/JournalInfo/{issn}")
    info: JournalInfo | None = None
    if data is not None:
        journals = data.get("journals", [])
        if journals:
            info = JournalInfo.model_validate(journals[0])
    cache.set(key, info, PANTER_CACHE_TTL)
    return info


def journal_info_bulk(issns: Sequence[str]) -> Sequence[JournalInfo]:
    """Fetch journal information for one or more ISSNs in a single request.

    Corresponds to ``POST /pricemonitor/coda/v1/JournalInfo``.

    Results are deduplicated server-side by freshness (``date_created`` /
    ``date_modified``), returning the most up-to-date row per ISSN.
    Unknown ISSNs are silently omitted from the response.

    Args:
        issns: One or more ISSN strings in ``NNNN-NNNN`` form.

    Returns:
        A (possibly empty) sequence of :class:`JournalInfo` instances,
        one per known ISSN.
    """
    data = _post("/JournalInfo", {"issn": list(issns)})
    if data is None:
        return []
    return [JournalInfo.model_validate(j) for j in data.get("journals", [])]


def search_journals(
    journal_name: str,
    publisher_id: int | None = None,
    publisher_name: str | None = None,
    page: int = 1,
    size: int = 50,
) -> tuple[Sequence[JournalSearchResult], int, int, int]:
    """Search journals by title, optionally restricted by publisher.

    Corresponds to ``POST /pricemonitor/coda/v1/JournalSearch``.

    The search uses a case-insensitive ``ILIKE %journal_name%`` match.
    Pagination is supported via ``page`` and ``size``.

    Args:
        journal_name: Required search term. Leading/trailing whitespace is
            trimmed server-side.
        publisher_id: Optional internal publisher ID. Takes precedence over
            ``publisher_name`` when both are provided.
        publisher_name: Optional publisher name (``ILIKE`` match without
            wildcard characters; callers should add ``%`` for pattern matching).
        page: Page number, 1-indexed. Defaults to 1.
        size: Results per page (1–100). Defaults to 50.

    Returns:
        A tuple ``(journals, total_count, total_pages, current_page)``.
        ``journals`` is a (possibly empty) sequence of
        :class:`JournalSearchResult` instances. On API error all numeric
        values default to 0 (except ``current_page`` which defaults to the
        requested ``page``).
    """
    body: dict[str, Any] = {"journalName": journal_name, "page": page, "size": size}
    if publisher_id is not None:
        body["publisherId"] = publisher_id
    elif publisher_name is not None:
        body["publisherName"] = publisher_name

    data = _post("/JournalSearch", body)
    if data is None:
        return [], 0, 0, page

    journals = [JournalSearchResult.model_validate(j) for j in data.get("journals", [])]
    return (
        journals,
        data.get("journals_total", 0),
        data.get("total_pages", 0),
        data.get("page", page),
    )


# ── Dedicated helper (used by the APC panel) ────────────────────


def fetch_journal_pricing(issn: str) -> Pricing | None:
    """Look up journal pricing data by ISSN, with caching.

    Combines :func:`journal_info` and :meth:`JournalInfo.pricing` into a
    single call. Both the underlying journal info and the resulting pricing
    are cached in Django's cache backend for :data:`PANTER_CACHE_TTL`
    seconds, so consecutive lookups for the same ISSN (and even the
    cross-process repeated lookups, depending on the configured backend)
    avoid hitting the external API.

    Args:
        issn: ISSN string in ``NNNN-NNNN`` form.

    Returns:
        :class:`Pricing` when the ISSN is found and ``additional_metadata``
        contains a valid ``pricing`` block; ``None`` when the ISSN is unknown,
        the API is unreachable, or the pricing data is absent or malformed.
    """
    key = f"panter:pricing:{issn}"
    cached = cache.get(key, _NOT_CACHED)
    if cached is not _NOT_CACHED:
        return cached
    info = journal_info(issn)
    pricing = info.pricing() if info is not None else None
    cache.set(key, pricing, PANTER_CACHE_TTL)
    return pricing

import pytest
from django.test.utils import override_settings
from tests.apps._doubles import RecordingCache

from coda.apps import version
from coda.apps.version import FAILURE_TTL, FRESH_TTL, has_newer_commit

# --- has_newer_commit --------------------------------------------------------


def test__has_newer_commit__short_sha_matches_full() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "8d68c555") is False


def test__has_newer_commit__different_short_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "abcdef1") is True


def test__has_newer_commit__tag_does_not_match_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "2026.01") is True


# --- check_update: caching contract ------------------------------------------

LATEST_SHA = "8d68c555e344cad5ec94e735b2be766e39f8e389"


class _FetchStub:
    """Stubbed GitHub call. Consecutive calls return the next of *results*,
    the last entry repeating. Records the branches it was asked about."""

    def __init__(self, *results: tuple[str | None, str | None]) -> None:
        self.requested: list[str] = []
        self._results = list(results) or [(LATEST_SHA, None)]

    def __call__(self, branch: str) -> tuple[str | None, str | None]:
        self.requested.append(branch)
        return self._results.pop(0) if len(self._results) > 1 else self._results[0]


@pytest.fixture
def stubbed_cache(monkeypatch: pytest.MonkeyPatch) -> RecordingCache:
    cache = RecordingCache()
    monkeypatch.setattr(version, "cache", cache)
    return cache


def test__check_update__given_nothing_cached__fetches_and_stores_upstream_sha(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    fetch = _FetchStub()
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    result = version.check_update("develop", "abc1234")

    assert result is True
    assert fetch.requested == ["develop"]
    assert stubbed_cache.values[version._sha_key("develop")] == LATEST_SHA
    assert stubbed_cache.timeouts[version._sha_key("develop")] == FRESH_TTL
    assert FRESH_TTL > FAILURE_TTL


def test__check_update__given_branch_with_slash__cache_key_stays_separator_free() -> None:
    """Branch names may contain "/"; a cache key may not."""
    assert "/" not in version._sha_key("feature/my-feature")


def test__check_update__given_cached_sha__skips_fetch_and_recompares_per_commit(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    """The cached value is the upstream SHA, not a verdict: a deploy inside the
    cache window must not inherit the previous commit's answer."""
    stubbed_cache.values[version._sha_key("develop")] = LATEST_SHA
    fetch = _FetchStub()
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    up_to_date = version.check_update("develop", LATEST_SHA[:8])
    behind = version.check_update("develop", "abcdef1")

    assert fetch.requested == []
    assert up_to_date is False
    assert behind is True


def test__check_update__given_failed_fetch__returns_false_and_backs_off(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    """An outage may not be retried on every page view."""
    fetch = _FetchStub((None, "502 Bad Gateway"))
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    result = version.check_update("develop", "abcdef1")

    assert result is False
    assert stubbed_cache.timeouts[version._error_key("develop")] == FAILURE_TTL
    assert version._sha_key("develop") not in stubbed_cache.values

    version.check_update("develop", "abcdef1")
    version.check_update("develop", "abcdef1")
    assert fetch.requested == ["develop"]  # throttled for FAILURE_TTL, not retried


def test__check_update__given_unreachable_cache__fetches_and_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead cache backend must not 500 the banner; behave like a miss."""

    class BrokenCache:
        def get(self, key: str, default: object = None) -> object:
            raise RuntimeError("cache backend is down")

        def set(self, key: str, value: str, timeout: int | None = None) -> None:
            raise RuntimeError("cache backend is down")

    fetch = _FetchStub()
    monkeypatch.setattr(version, "cache", BrokenCache())
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    assert version.check_update("develop", "abc1234") is True
    assert fetch.requested == ["develop"]


def test__check_update__given_cached_sha_from_previous_failure_window__recovers(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    """After the backoff lapses, a successful fetch is retried and cached."""
    fetch = _FetchStub((None, "502 Bad Gateway"), (LATEST_SHA, None))
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)
    assert version.check_update("develop", "abcdef1") is False

    del stubbed_cache.values[version._error_key("develop")]  # backoff lapses

    assert version.check_update("develop", "abc1234") is True
    assert fetch.requested == ["develop", "develop"]
    assert stubbed_cache.values[version._sha_key("develop")] == LATEST_SHA


@override_settings(CODA_UPDATE_CHECK=False)
def test__check_update__given_update_check_disabled__skips_cache_and_network(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    fetch = _FetchStub()
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    assert version.check_update("develop", "abc1234") is False
    assert fetch.requested == []
    assert stubbed_cache.values == {}

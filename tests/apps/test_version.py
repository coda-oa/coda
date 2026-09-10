import pytest
from django.test.utils import override_settings

from tests.apps._doubles import (
    BrokenCache,
    InMemoryVersionInfoProvider,
    RecordingCache,
)
from coda.apps.version import (
    SystemVersionInfoProvider,
    check_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
    has_newer_commit,
)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> InMemoryVersionInfoProvider:
    p = InMemoryVersionInfoProvider()
    monkeypatch.setattr("coda.apps.version._provider", p)
    return p


def test__get_branch__given_default_provider__returns_develop(
    provider: InMemoryVersionInfoProvider,
) -> None:
    assert get_branch() == "develop"


def test__get_branch__given_custom_branch__returns_custom_value(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.branch = "feature/my-feature"
    assert get_branch() == "feature/my-feature"


def test__get_repo__given_default_provider__returns_default_repo(
    provider: InMemoryVersionInfoProvider,
) -> None:
    assert get_repo() == "coda-oa/coda"


def test__get_repo__given_upstream_fork__returns_fork_repo(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.repo = "fjen/coda"
    assert get_repo() == "fjen/coda"


def test__get_version_tag__given_no_tag__returns_none(
    provider: InMemoryVersionInfoProvider,
) -> None:
    assert get_version_tag() is None


def test__get_version_tag__given_tag_exists__returns_tag(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.version_tag = "2026.01"
    assert get_version_tag() == "2026.01"


def test__check_update__given_provider_returns_update_available__returns_update_available(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.update_info = {
        "update_available": True,
        "latest_commit": "abcdef1234567890abcdef1234567890abcdef12",
    }
    result = check_update("develop", "oldcommit123")
    assert result["update_available"] is True
    assert result["latest_commit"] == "abcdef1234567890abcdef1234567890abcdef12"


def test__check_update__given_provider_returns_no_update__returns_false(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.update_info = {"update_available": False}
    result = check_update("develop", "abc123")
    assert result["update_available"] is False


def test__check_update__given_provider_returns_error__returns_no_update(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.update_info = {"update_available": False, "error": "Network error"}
    result = check_update("develop", "abc")
    assert result["update_available"] is False
    assert "error" in result


def test__get_commit_sha__given_tag_version__returns_raw_sha(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.version = "2026.01"
    provider.version_tag = "2026.01"
    provider.commit_sha = "8d68c555e344cad5ec94e735b2be766e39f8e389"
    assert get_commit_sha() == "8d68c555e344cad5ec94e735b2be766e39f8e389"


def test__has_newer_commit__short_sha_matches_full() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "8d68c555") is False


def test__has_newer_commit__different_short_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "abcdef1") is True


def test__has_newer_commit__tag_does_not_match_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "2026.01") is True


# --- SystemVersionInfoProvider.check_update: caching contract ----------------

LATEST_SHA = "8d68c555e344cad5ec94e735b2be766e39f8e389"


def _system_provider(
    monkeypatch: pytest.MonkeyPatch,
    cache: RecordingCache | BrokenCache,
    *fetch_results: tuple[str | None, str | None],
) -> tuple[SystemVersionInfoProvider, list[str]]:
    """Provider with an injected cache and a stubbed GitHub call.

    Consecutive calls return the next of *fetch_results*, the last entry
    repeating. Returns the provider and the branches the stub was asked about.
    """
    provider = SystemVersionInfoProvider()
    requested: list[str] = []
    results = list(fetch_results) or [(LATEST_SHA, None)]

    def fake_fetch(branch: str) -> tuple[str | None, str | None]:
        requested.append(branch)
        return results.pop(0) if len(results) > 1 else results[0]

    monkeypatch.setattr(provider, "_cache", cache)
    monkeypatch.setattr(provider, "_fetch_latest_commit", fake_fetch)
    return provider, requested


def test__check_update__given_nothing_cached__stores_upstream_sha_fresh_and_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = SystemVersionInfoProvider
    cache = RecordingCache()
    provider, requested = _system_provider(monkeypatch, cache)

    result = provider.check_update("develop", "abc1234")

    assert requested == ["develop"]
    assert result == {"update_available": True, "latest_commit": LATEST_SHA}
    assert cache.values[keys._fresh_key("develop")] == LATEST_SHA
    assert cache.timeouts[keys._fresh_key("develop")] == keys.FRESH_TTL
    assert cache.timeouts[keys._stale_key("develop")] == keys.STALE_TTL
    # The stale mirror only exists to outlive the fresh entry; equal TTLs make it dead weight.
    assert keys.STALE_TTL > keys.FRESH_TTL > keys.FAILURE_TTL


def test__check_update__given_branch_with_slash__cache_key_stays_separator_free() -> None:
    """Branch names may contain "/"; a cache key may not."""
    assert "/" not in SystemVersionInfoProvider._fresh_key("feature/my-feature")


def test__check_update__given_cached_sha__skips_fetch_and_recompares_per_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cached value is the upstream SHA, not a verdict: a deploy inside the
    cache window must not inherit the previous commit's answer."""
    cache = RecordingCache({SystemVersionInfoProvider._fresh_key("develop"): LATEST_SHA})
    provider, requested = _system_provider(monkeypatch, cache)

    up_to_date = provider.check_update("develop", LATEST_SHA[:8])
    behind = provider.check_update("develop", "abcdef1")

    assert requested == []
    assert up_to_date == {"update_available": False, "latest_commit": LATEST_SHA}
    assert behind == {"update_available": True, "latest_commit": LATEST_SHA}


def test__check_update__given_expired_cache_and_failed_fetch__degrades_and_backs_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One outage may not blank the banner for an hour, nor be retried per view."""
    keys = SystemVersionInfoProvider
    cache = RecordingCache()
    provider, requested = _system_provider(
        monkeypatch, cache, (LATEST_SHA, None), (None, "502 Bad Gateway")
    )
    assert provider.check_update("develop", "abc1234")["update_available"] is True

    del cache.values[keys._fresh_key("develop")]  # its TTL lapses during the outage
    result = provider.check_update("develop", "abcdef1")

    assert result == {
        "update_available": True,  # served from the last known-good SHA
        "latest_commit": LATEST_SHA,
        "error": "502 Bad Gateway",
    }
    assert cache.timeouts[keys._error_key("develop")] == keys.FAILURE_TTL
    assert keys._fresh_key("develop") not in cache.values

    provider.check_update("develop", "abcdef1")
    assert requested == ["develop", "develop"]  # throttled for FAILURE_TTL, not retried


def test__check_update__given_unreachable_cache__still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, requested = _system_provider(monkeypatch, BrokenCache())

    result = provider.check_update("develop", "abc1234")

    assert requested == ["develop"]
    assert result == {"update_available": True, "latest_commit": LATEST_SHA}


@override_settings(CODA_UPDATE_CHECK=False)
def test__check_update__given_update_check_disabled__skips_cache_and_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = RecordingCache()
    provider, requested = _system_provider(monkeypatch, cache)

    assert provider.check_update("develop", "abc1234") == {"update_available": False}
    assert requested == []
    assert cache.values == {}

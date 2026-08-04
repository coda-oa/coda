import pytest

from tests.apps._doubles import InMemoryVersionInfoProvider
from coda.apps.version import (
    check_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
    has_newer_commit,
)
from django.core.cache import cache as django_cache
from coda.apps.version import SystemVersionInfoProvider


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


def test__check_update__given_cache_miss__returns_optimistic_false() -> None:

    django_cache.delete("version_update_develop")

    provider = SystemVersionInfoProvider()
    result = provider.check_update("develop", "abc1234")

    assert result == {"update_available": False}


def test__has_newer_commit__short_sha_matches_full() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "8d68c555") is False


def test__has_newer_commit__different_short_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "abcdef1") is True


def test__has_newer_commit__tag_does_not_match_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "2026.01") is True

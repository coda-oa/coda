import pytest

from tests.apps._doubles import InMemoryVersionInfoProvider
from coda.apps.version import check_update, get_branch, get_repo, get_version_tag


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


def test__check_update__given_newer_commit__returns_update_available(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.update_info = {
        "update_available": True,
        "latest_commit": "abcdef1234567890abcdef1234567890abcdef12",
    }
    result = check_update("develop", "oldcommit123")
    assert result["update_available"] is True
    assert result["latest_commit"] == "abcdef1234567890abcdef1234567890abcdef12"


def test__check_update__given_same_commit__returns_no_update(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.update_info = {"update_available": False}
    result = check_update("develop", "abc123")
    assert result["update_available"] is False


def test__check_update__given_github_api_fails__returns_no_update(
    provider: InMemoryVersionInfoProvider,
) -> None:
    provider.update_info = {"update_available": False, "error": "Network error"}
    result = check_update("develop", "abc")
    assert result["update_available"] is False
    assert "error" in result

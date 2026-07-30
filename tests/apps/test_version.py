from unittest import mock

from coda.apps.version import check_update, get_branch


def test_get_branch_GivenGitAvailable_ShouldReturnBranchName() -> None:
    with mock.patch("coda.apps.version.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "develop\n"
        assert get_branch() == "develop"


def test_get_branch_GivenGitFails_ShouldReturnUnknown() -> None:
    with mock.patch("coda.apps.version.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        assert get_branch() == "unknown"


def test_check_update_GivenNewerCommit_ShouldReturnUpdateAvailable() -> None:
    with (
        mock.patch("coda.apps.version.httpx.get") as mock_get,
        mock.patch("coda.apps.version.cache") as mock_cache,
    ):
        mock_cache.get.return_value = None
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "commit": {"sha": "abcdef1234567890abcdef1234567890abcdef12"}
        }
        mock_get.return_value = mock_response

        result = check_update("develop", "oldcommit123")

        assert result["update_available"] is True
        assert result["latest_commit"] == "abcdef1234567890abcdef1234567890abcdef12"


def test_check_update_GivenSameCommit_ShouldReturnNoUpdate() -> None:
    sha = "abcdef1234567890abcdef1234567890abcdef12"
    with (
        mock.patch("coda.apps.version.httpx.get") as mock_get,
        mock.patch("coda.apps.version.cache") as mock_cache,
    ):
        mock_cache.get.return_value = None
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"commit": {"sha": sha}}
        mock_get.return_value = mock_response

        result = check_update("develop", sha)

        assert result["update_available"] is False


def test_check_update_GivenGitHubApiFails_ShouldReturnNoUpdate() -> None:
    with (
        mock.patch("coda.apps.version.httpx.get") as mock_get,
        mock.patch("coda.apps.version.cache") as mock_cache,
    ):
        mock_cache.get.return_value = None
        mock_get.side_effect = Exception("Network error")

        result = check_update("develop", "abc")

        assert result["update_available"] is False
        assert "error" in result

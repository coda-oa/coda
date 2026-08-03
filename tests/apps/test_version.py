from unittest import mock

from coda.apps.version import check_update, get_branch, get_repo, get_version_tag


def test__get_branch__given_git_fails_but_branch_file_exists__returns_branch_from_file() -> None:
    with (
        mock.patch("coda.apps.version.subprocess.run") as mock_run,
        mock.patch("coda.apps.version.Path") as mock_path,
    ):
        mock_run.side_effect = FileNotFoundError()
        mock_path.return_value.is_file.return_value = True
        mock_path.return_value.read_text.return_value = "stable\n"
        assert get_branch() == "stable"


def test__get_version_tag__given_tag_exists__returns_tag() -> None:
    with mock.patch("coda.apps.version.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "2026.01\n"
        assert get_version_tag() == "2026.01"


def test__get_version_tag__given_no_tag__returns_none() -> None:
    with mock.patch("coda.apps.version.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert get_version_tag() is None


def test__get_version_tag__given_git_fails__returns_none() -> None:
    with (
        mock.patch("coda.apps.version.subprocess.run") as mock_run,
        mock.patch("coda.apps.version.Path") as mock_path,
    ):
        mock_run.side_effect = FileNotFoundError()
        mock_path.return_value.is_file.return_value = False
        assert get_version_tag() is None


def test__get_version_tag__given_git_fails_but_tag_file_exists__returns_tag_from_file() -> None:
    with (
        mock.patch("coda.apps.version.subprocess.run") as mock_run,
        mock.patch("coda.apps.version.Path") as mock_path,
    ):
        mock_run.side_effect = FileNotFoundError()
        mock_path.return_value.is_file.return_value = True
        mock_path.return_value.read_text.return_value = "2026.01\n"
        assert get_version_tag() == "2026.01"


def test__get_repo__given_upstream_remote__uses_upstream() -> None:
    mock_run = mock.MagicMock()
    mock_run.side_effect = [
        mock.MagicMock(returncode=0, stdout="refs/remotes/fjen/feature/version-info\n"),
        mock.MagicMock(returncode=0, stdout="https://github.com/fjen/coda.git\n"),
    ]
    with mock.patch("coda.apps.version.subprocess.run", mock_run):
        assert get_repo() == "fjen/coda"


def test__get_repo__given_no_upstream_falls_back_to_origin_with_https() -> None:
    mock_run = mock.MagicMock()
    mock_run.side_effect = [
        mock.MagicMock(returncode=1, stdout=""),
        mock.MagicMock(returncode=0, stdout="https://github.com/coda-oa/coda.git\n"),
    ]
    with mock.patch("coda.apps.version.subprocess.run", mock_run):
        assert get_repo() == "coda-oa/coda"


def test__get_repo__given_no_upstream_falls_back_to_origin_with_ssh() -> None:
    mock_run = mock.MagicMock()
    mock_run.side_effect = [
        mock.MagicMock(returncode=1, stdout=""),
        mock.MagicMock(returncode=0, stdout="git@github.com:coda-oa/coda.git\n"),
    ]
    with mock.patch("coda.apps.version.subprocess.run", mock_run):
        assert get_repo() == "coda-oa/coda"


def test__get_repo__given_git_fails_but_repo_file_exists__returns_repo_from_file() -> None:
    with (
        mock.patch("coda.apps.version.subprocess.run") as mock_run,
        mock.patch("coda.apps.version.Path") as mock_path,
    ):
        mock_run.side_effect = FileNotFoundError()
        mock_path.return_value.is_file.return_value = True
        mock_path.return_value.read_text.return_value = "my-fork/coda\n"
        assert get_repo() == "my-fork/coda"


def test__get_repo__given_git_fails_and_no_file__returns_default() -> None:
    with (
        mock.patch("coda.apps.version.subprocess.run") as mock_run,
        mock.patch("coda.apps.version.Path") as mock_path,
    ):
        mock_run.side_effect = FileNotFoundError()
        mock_path.return_value.is_file.return_value = False
        assert get_repo() == "coda-oa/coda"


def test__get_branch__given_git_available__returns_branch_name() -> None:
    with mock.patch("coda.apps.version.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "develop\n"
        assert get_branch() == "develop"


def test__get_branch__given_git_fails__returns_unknown() -> None:
    with mock.patch("coda.apps.version.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        assert get_branch() == "unknown"


def test__check_update__given_newer_commit__returns_update_available() -> None:
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


def test__check_update__given_same_commit__returns_no_update() -> None:
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


def test__check_update__given_github_api_fails__returns_no_update() -> None:
    with (
        mock.patch("coda.apps.version.httpx.get") as mock_get,
        mock.patch("coda.apps.version.cache") as mock_cache,
    ):
        mock_cache.get.return_value = None
        mock_get.side_effect = Exception("Network error")

        result = check_update("develop", "abc")

        assert result["update_available"] is False
        assert "error" in result

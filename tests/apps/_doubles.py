"""Test doubles for version module tests."""

from coda.apps.version import UpdateCheckResult


class InMemoryVersionInfoProvider:
    """In-memory implementation of VersionInfoProvider for testing."""

    def __init__(self) -> None:
        self.branch = "develop"
        self.repo = "coda-oa/coda"
        self.version = "abc1234"
        self.version_tag: str | None = None
        self.update_info: UpdateCheckResult = {"update_available": False}

    def get_branch(self) -> str:
        return self.branch

    def get_repo(self) -> str:
        return self.repo

    def get_version(self) -> str:
        return self.version

    def get_version_tag(self) -> str | None:
        return self.version_tag

    def check_update(self, branch: str, current_commit: str) -> UpdateCheckResult:
        return self.update_info

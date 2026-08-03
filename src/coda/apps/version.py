from functools import lru_cache
from pathlib import Path
import subprocess
from typing import Protocol, TypedDict
from typing import NotRequired

from urllib.parse import quote, urlparse

import httpx
from django.conf import settings
from django.core.cache import cache


class VersionInfoProvider(Protocol):
    """Contract for version/branch/repo information and update checks."""

    def get_branch(self) -> str: ...

    def get_repo(self) -> str: ...

    def get_version(self) -> str: ...

    def get_version_tag(self) -> str | None: ...

    def check_update(self, branch: str, current_commit: str) -> "UpdateCheckResult": ...


class UpdateCheckResult(TypedDict):
    update_available: bool
    latest_commit: NotRequired[str]
    error: NotRequired[str]


def has_newer_commit(latest_sha: str, current_commit: str) -> bool:
    """Return True if *latest_sha* (from GitHub) differs from *current_commit*.

    *current_commit* may be a short SHA (e.g. ``"8d68c555"``), a full SHA
    (e.g. ``"8d68c555e344cad5ec94e735b2be766e39f8e389"``), or a tag name
    (e.g. ``"2026.01"``).  Short SHAs are matched by prefix so that comparing
    a full remote SHA against a short local SHA works correctly.
    """
    return not latest_sha.startswith(current_commit)


def _parse_github_url(url: str) -> str | None:
    for prefix in ["https://github.com/", "git@github.com:"]:
        if url.startswith(prefix):
            repo = url.removeprefix(prefix)
            if repo.endswith(".git"):
                repo = repo.removesuffix(".git")
            return repo
    return None


class SystemVersionInfoProvider:
    """Real implementation using git, httpx, Django cache, and baked files."""

    def __init__(self) -> None:
        self._cache = cache

    def get_version_tag(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        tag_path = Path(settings.BASE_DIR / "TAG")
        if tag_path.is_file():
            return tag_path.read_text().strip()
        return None

    def get_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        branch_path = Path(settings.BASE_DIR / "BRANCH")
        if branch_path.is_file():
            return branch_path.read_text().strip()
        return "unknown"

    def get_repo(self) -> str:
        remotes_to_try: list[str] = []
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--symbolic-full-name", "@{upstream}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                ref = result.stdout.strip()
                parts = ref.split("/")
                if len(parts) >= 4 and parts[0] == "refs" and parts[1] == "remotes":
                    remotes_to_try.append(parts[2])
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        remotes_to_try.append("origin")

        for remote in remotes_to_try:
            try:
                result = subprocess.run(
                    ["git", "remote", "get-url", remote],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    repo = _parse_github_url(result.stdout.strip())
                    if repo is not None:
                        return repo
            except (FileNotFoundError, subprocess.SubprocessError):
                continue

        repo_path = Path(settings.BASE_DIR / "REPO")
        if repo_path.is_file():
            return repo_path.read_text().strip()
        return "coda-oa/coda"

    @lru_cache(maxsize=1)
    def get_version(self) -> str:
        git_commands = [
            ["git", "describe", "--tags", "--exact-match"],
            ["git", "rev-parse", "--short", "HEAD"],
        ]

        for cmd in git_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return result.stdout.strip()
            except (FileNotFoundError, subprocess.SubprocessError):
                continue

        version_path = settings.BASE_DIR / "VERSION"
        if version_path.is_file():
            return version_path.read_text().strip()

        return "unknown"

    def check_update(self, branch: str, current_commit: str) -> UpdateCheckResult:
        cache_key = f"version_update_{branch}"
        cached: UpdateCheckResult | None = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            repo = self.get_repo()
            url = f"https://api.github.com/repos/{repo}/branches/{quote(branch, safe='')}"
            parsed = urlparse(url)
            if parsed.hostname != "api.github.com" or not parsed.path.startswith("/repos/"):
                raise ValueError(f"Invalid repository URL: {url!r}")
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            latest_sha = response.json()["commit"]["sha"]
            result: UpdateCheckResult = {
                "update_available": has_newer_commit(latest_sha, current_commit),
                "latest_commit": latest_sha,
            }
        except Exception as e:
            result = {"update_available": False, "error": str(e)}

        self._cache.set(cache_key, result, 3600)
        return result


_provider: VersionInfoProvider = SystemVersionInfoProvider()


def get_branch() -> str:
    return _provider.get_branch()


def get_repo() -> str:
    return _provider.get_repo()


def get_version() -> str:
    return _provider.get_version()


def get_version_tag() -> str | None:
    return _provider.get_version_tag()


def check_update(branch: str, current_commit: str) -> UpdateCheckResult:
    return _provider.check_update(branch, current_commit)

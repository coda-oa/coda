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
        return self._git(["describe", "--tags", "--exact-match"]) or self._baked_file("TAG")

    def get_branch(self) -> str:
        return (
            self._git(["rev-parse", "--abbrev-ref", "HEAD"])
            or self._baked_file("BRANCH")
            or "unknown"
        )

    def get_repo(self) -> str:
        return (
            self._repo_from_upstream()
            or self._repo_from_remote("origin")
            or self._baked_repo()
            or "coda-oa/coda"
        )

    @lru_cache(maxsize=1)
    def get_version(self) -> str:
        return (
            self._git(["describe", "--tags", "--exact-match"])
            or self._git(["rev-parse", "--short", "HEAD"])
            or self._baked_file("VERSION")
            or "unknown"
        )

    def check_update(self, branch: str, current_commit: str) -> UpdateCheckResult:
        cache_key = f"version_update_{branch}"
        cached: UpdateCheckResult | None = self._cache.get(cache_key)
        if cached is not None:
            return cached

        latest_sha, error = self._fetch_latest_commit(branch)
        result: UpdateCheckResult = {
            "update_available": (
                has_newer_commit(latest_sha, current_commit) if latest_sha else False
            ),
        }
        if latest_sha:
            result["latest_commit"] = latest_sha
        if error:
            result["error"] = error

        self._cache.set(cache_key, result, 3600)
        return result

    def _git(self, args: list[str]) -> str | None:
        try:
            result = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        return None

    def _baked_file(self, name: str) -> str | None:
        path = Path(settings.BASE_DIR / name)
        if path.is_file():
            return path.read_text().strip()
        return None

    def _repo_from_remote(self, name: str) -> str | None:
        url = self._git(["remote", "get-url", name])
        return _parse_github_url(url) if url else None

    def _upstream_remote_name(self) -> str | None:
        ref = self._git(["rev-parse", "--symbolic-full-name", "@{upstream}"])
        if ref is None:
            return None
        parts = ref.split("/")
        if len(parts) >= 4 and parts[0] == "refs" and parts[1] == "remotes":
            return parts[2]
        return None

    def _baked_repo(self) -> str | None:
        repo = self._baked_file("REPO")
        if repo is None:
            return None
        parsed = urlparse(f"https://api.github.com/repos/{repo}")
        if parsed.hostname == "api.github.com" and parsed.path.startswith("/repos/"):
            return repo
        return None

    def _repo_from_upstream(self) -> str | None:
        remote = self._upstream_remote_name()
        return self._repo_from_remote(remote) if remote else None

    def _fetch_latest_commit(self, branch: str) -> tuple[str | None, str | None]:
        try:
            repo = self.get_repo()
            url = f"https://api.github.com/repos/{repo}/branches/{quote(branch, safe='')}"
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            return response.json()["commit"]["sha"], None
        except httpx.HTTPStatusError as e:
            return None, str(e)
        except (httpx.RequestError, KeyError, ValueError) as e:
            return None, str(e)


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

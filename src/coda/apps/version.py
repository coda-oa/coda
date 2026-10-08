from functools import lru_cache
from pathlib import Path
import logging
import subprocess
from typing import Protocol, TypedDict
from typing import NotRequired

from urllib.parse import quote, urlparse

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class VersionInfoProvider(Protocol):
    """Contract for version/branch/repo information and update checks."""

    def get_branch(self) -> str: ...

    def get_repo(self) -> str: ...

    def get_version(self) -> str: ...

    def get_version_tag(self) -> str | None: ...

    def get_commit_sha(self) -> str: ...

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
    """Real implementation using git, httpx, Django cache, and baked files.

    The two primitives that do I/O, ``_git`` and ``_baked_file``, are memoised per
    process, so the getters below stay plain functions and run git at most once
    per command.
    """

    #: How long a fetched upstream SHA is considered fresh.
    FRESH_TTL = 3600 * 24
    #: How long a failed lookup is remembered, so a single GitHub hiccup neither
    #: blanks the banner for a whole refresh window nor gets retried per request.
    FAILURE_TTL = 300
    #: How long the last known-good SHA may still answer once it is stale. Derived
    #: from ``FRESH_TTL`` so the fallback cannot expire before the entry it backs up.
    STALE_TTL = 4 * FRESH_TTL

    def __init__(self) -> None:
        self._cache = cache

    def get_version_tag(self) -> str | None:
        return self._git(("describe", "--tags", "--exact-match")) or self._baked_file("TAG")

    def get_branch(self) -> str:
        return (
            self._git(("rev-parse", "--abbrev-ref", "HEAD"))
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

    def get_version(self) -> str:
        return (
            self.get_version_tag()
            or self._git(("rev-parse", "--short", "HEAD"))
            or self._baked_file("VERSION")
            or "unknown"
        )

    def get_commit_sha(self) -> str:
        return self._git(("rev-parse", "HEAD")) or self._baked_file("SHA") or "unknown"

    def check_update(self, branch: str, current_commit: str) -> UpdateCheckResult:
        """Report whether *branch* has commits beyond *current_commit*.

        Only the upstream SHA is cached, never the verdict, so a deploy landing
        inside the cache window is not answered with the previous commit's result.
        """
        if not settings.CODA_UPDATE_CHECK:
            return {"update_available": False}

        latest_sha, error = self._latest_commit(branch)
        result: UpdateCheckResult = {"update_available": False}
        if latest_sha:
            result["update_available"] = has_newer_commit(latest_sha, current_commit)
            result["latest_commit"] = latest_sha
        if error:
            result["error"] = error
        return result

    def _latest_commit(self, branch: str) -> tuple[str | None, str | None]:
        """Latest upstream SHA for *branch*, plus the error if none could be had.

        A fresh cache entry wins. Otherwise a recent failure is respected rather
        than retried on every page view, and the last known-good SHA answers in
        the meantime — a stale banner beats no banner at all.
        """
        latest_sha = self._cache_get(self._fresh_key(branch))
        if latest_sha is not None:
            return latest_sha, None

        error = self._cache_get(self._error_key(branch))
        if error is None:
            latest_sha, error = self._fetch_latest_commit(branch)
            if latest_sha is not None:
                self._cache_set(self._fresh_key(branch), latest_sha, self.FRESH_TTL)
                self._cache_set(self._stale_key(branch), latest_sha, self.STALE_TTL)
                return latest_sha, None
            self._cache_set(self._error_key(branch), error or "unknown error", self.FAILURE_TTL)

        return self._cache_get(self._stale_key(branch)), error

    @staticmethod
    def _fresh_key(branch: str) -> str:
        return f"github_branch_sha_{quote(branch, safe='')}"

    @staticmethod
    def _stale_key(branch: str) -> str:
        return f"github_branch_sha_stale_{quote(branch, safe='')}"

    @staticmethod
    def _error_key(branch: str) -> str:
        return f"github_branch_error_{quote(branch, safe='')}"

    def _cache_get(self, key: str) -> str | None:
        """Read the cache, treating an unreachable backend as a miss.

        A dead cache is not worth a 500 on a decorative banner, and the built-in
        backends offer no "ignore exceptions" switch to lean on.
        """
        try:
            value: object = self._cache.get(key)
        except Exception:
            logger.warning("update-check cache read failed for %r", key, exc_info=True)
            return None
        return value if isinstance(value, str) else None

    def _cache_set(self, key: str, value: str, timeout: int) -> None:
        try:
            self._cache.set(key, value, timeout)
        except Exception:
            logger.warning("update-check cache write failed for %r", key, exc_info=True)

    @staticmethod
    @lru_cache(maxsize=16)
    def _git(args: tuple[str, ...]) -> str | None:
        try:
            result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        return None

    @staticmethod
    @lru_cache(maxsize=8)
    def _baked_file(name: str) -> str | None:
        path = Path(settings.BASE_DIR / name)
        if path.is_file():
            return path.read_text().strip()
        return None

    def _repo_from_remote(self, name: str) -> str | None:
        url = self._git(("remote", "get-url", name))
        return _parse_github_url(url) if url else None

    def _upstream_remote_name(self) -> str | None:
        ref = self._git(("rev-parse", "--symbolic-full-name", "@{upstream}"))
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
            response = httpx.get(url, timeout=3)
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


def get_commit_sha() -> str:
    return _provider.get_commit_sha()


def check_update(branch: str, current_commit: str) -> UpdateCheckResult:
    return _provider.check_update(branch, current_commit)

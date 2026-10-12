"""Version information and update checking.

The version getters resolve the running deployment via git (dev) or files
baked into the image at build time (production). The update check compares the
current commit against the upstream branch on GitHub; only the upstream SHA is
cached, never the verdict, so a deploy landing inside the cache window is not
answered with the previous commit's result.
"""

import logging
import subprocess
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: How long a fetched upstream SHA is considered fresh.
FRESH_TTL = 3600 * 24
#: How long a failed lookup is remembered, so a single GitHub hiccup is neither
#: retried on every page view nor hides the banner for a whole refresh window.
FAILURE_TTL = 300
DEFAULT_REPO = "coda-oa/coda"


def get_version_tag() -> str | None:
    return _git(("describe", "--tags", "--exact-match")) or _baked_file("TAG")


def get_branch() -> str:
    return _git(("rev-parse", "--abbrev-ref", "HEAD")) or _baked_file("BRANCH") or "unknown"


def get_repo() -> str:
    return _repo_from_upstream() or _repo_from_remote("origin") or _baked_repo() or DEFAULT_REPO


def get_version() -> str:
    return (
        get_version_tag()
        or _git(("rev-parse", "--short", "HEAD"))
        or _baked_file("VERSION")
        or "unknown"
    )


def get_commit_sha() -> str:
    return _git(("rev-parse", "HEAD")) or _baked_file("SHA") or "unknown"


def has_newer_commit(latest_sha: str, current_commit: str) -> bool:
    """Return True if *latest_sha* (from GitHub) differs from *current_commit*.

    *current_commit* may be a short SHA (e.g. ``"8d68c555"``), a full SHA, or a
    tag name. Short SHAs are matched by prefix so that comparing a full remote
    SHA against a short local SHA works correctly.
    """
    return not latest_sha.startswith(current_commit)


def check_update(branch: str, current_commit: str) -> bool:
    """Report whether *branch* on GitHub has commits beyond *current_commit*.

    A failed lookup is remembered for FAILURE_TTL rather than retried on every
    page view; while it lasts, the banner simply stays hidden.
    """
    if not settings.CODA_UPDATE_CHECK:
        return False

    key = _sha_key(branch)
    latest_sha = _cache_get(key)
    if latest_sha is None and not _cache_get(_error_key(branch)):
        latest_sha, error = _fetch_latest_commit(branch)
        if latest_sha is not None:
            _cache_set(key, latest_sha, FRESH_TTL)
        else:
            _cache_set(_error_key(branch), error or "unknown error", FAILURE_TTL)
            logger.warning("update check for branch %r failed: %s", branch, error)

    return has_newer_commit(latest_sha, current_commit) if latest_sha else False


def _sha_key(branch: str) -> str:
    return f"github_branch_sha_{quote(branch, safe='')}"


def _error_key(branch: str) -> str:
    return f"github_branch_error_{quote(branch, safe='')}"


def _cache_get(key: str) -> str | None:
    """Read the cache, treating an unreachable backend as a miss.

    A dead cache is not worth a 500 on a decorative banner.
    """
    try:
        value: object = cache.get(key)
    except Exception:
        logger.warning("update-check cache read failed for %r", key, exc_info=True)
        return None
    return value if isinstance(value, str) else None


def _cache_set(key: str, value: str, timeout: int) -> None:
    try:
        cache.set(key, value, timeout)
    except Exception:
        logger.warning("update-check cache write failed for %r", key, exc_info=True)


def _fetch_latest_commit(branch: str) -> tuple[str | None, str | None]:
    try:
        url = f"https://api.github.com/repos/{get_repo()}/branches/{quote(branch, safe='')}"
        response = httpx.get(url, timeout=3)
        response.raise_for_status()
        sha: str = response.json()["commit"]["sha"]
        return sha, None
    except httpx.HTTPStatusError as e:
        return None, str(e)
    except (httpx.RequestError, KeyError, ValueError) as e:
        return None, str(e)


@lru_cache(maxsize=16)
def _git(args: tuple[str, ...]) -> str | None:
    """Run one git command. Memoised per process: the getters run on every
    template render via the context processor."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=5, check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


@lru_cache(maxsize=8)
def _baked_file(name: str) -> str | None:
    path = Path(settings.BASE_DIR / name)
    if path.is_file():
        return path.read_text().strip()
    return None


def _parse_github_url(url: str) -> str | None:
    for prefix in ["https://github.com/", "git@github.com:"]:
        if url.startswith(prefix):
            repo = url.removeprefix(prefix)
            if repo.endswith(".git"):
                repo = repo.removesuffix(".git")
            return repo
    return None


def _repo_from_remote(name: str) -> str | None:
    url = _git(("remote", "get-url", name))
    return _parse_github_url(url) if url else None


def _upstream_remote_name() -> str | None:
    ref = _git(("rev-parse", "--symbolic-full-name", "@{upstream}"))
    if ref is None:
        return None
    parts = ref.split("/")
    if len(parts) >= 4 and parts[0] == "refs" and parts[1] == "remotes":
        return parts[2]
    return None


def _baked_repo() -> str | None:
    repo = _baked_file("REPO")
    if repo is None:
        return None
    parsed = urlparse(f"https://api.github.com/repos/{repo}")
    if parsed.hostname == "api.github.com" and parsed.path.startswith("/repos/"):
        return repo
    return None


def _repo_from_upstream() -> str | None:
    remote = _upstream_remote_name()
    return _repo_from_remote(remote) if remote else None

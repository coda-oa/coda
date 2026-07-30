from functools import lru_cache
from pathlib import Path
import subprocess
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache


def get_version_tag() -> str | None:
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


def get_branch() -> str:
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


@lru_cache(maxsize=1)
def check_update(branch: str, current_commit: str) -> dict[str, Any]:
    cache_key = f"version_update_{branch}"
    cached: dict[str, Any] | None = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        url = f"https://api.github.com/repos/coda-oa/coda/branches/{branch}"
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        latest_sha = response.json()["commit"]["sha"]
        result = {
            "update_available": latest_sha != current_commit,
            "latest_commit": latest_sha,
        }
    except Exception as e:
        result = {"update_available": False, "error": str(e)}

    cache.set(cache_key, result, 3600)
    return result


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the current CODA version string.

    Resolution order:
    1. ``git describe --tags --exact-match`` (tagged commit, any env)
    2. ``git rev-parse --short HEAD`` (uncommitted, any env)
    3. ``VERSION`` file next to project root (baked into production image)
    4. ``"unknown"`` (last resort)
    """
    # Try git commands in order of preference
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

    # Fallback to baked VERSION file
    version_path = settings.BASE_DIR / "VERSION"
    if version_path.is_file():
        return version_path.read_text().strip()

    return "unknown"

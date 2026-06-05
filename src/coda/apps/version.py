from functools import lru_cache
import subprocess

from django.conf import settings


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

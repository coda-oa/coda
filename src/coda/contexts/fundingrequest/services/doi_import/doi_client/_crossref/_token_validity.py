"""Persisted validity flag for the Crossref Plus token.

When Crossref refuses the stored Plus key (401/403, e.g. an expired key),
keeping it in the rotation means every fetch pays the rejection round-trip
and fails outright. On the first rejection the fetch paths mark the token
invalid; from then on requests go out without the Plus header, degrading to
the polite pool (email identification only). The flag resets when:

- the user saves a new key in the form, or
- the user runs "Check key status" and Crossref accepts the key.

Unlike a timer-based circuit breaker, recovery is user-driven and the flag
survives process restarts and multiple gunicorn workers.
"""

import logging

AUTH_REJECT_STATUSES = frozenset({401, 403})

logger = logging.getLogger(__name__)


def is_token_marked_invalid() -> bool:
    """Whether the stored token was rejected and is excluded from requests."""
    from coda.apps.preferences.models import GlobalPreferences

    try:
        return (
            GlobalPreferences.objects.values_list("crossref_plus_api_token_valid", flat=True).get()
            is False
        )
    except GlobalPreferences.DoesNotExist:
        return False


def mark_token_invalid() -> None:
    """Record that Crossref rejected the stored token.

    Best-effort: without a usable database (bare unit tests, CLI), fetches
    must still surface their original error instead of a write failure.
    """
    from coda.apps.preferences.models import GlobalPreferences

    try:
        GlobalPreferences.objects.update_or_create(
            defaults={"crossref_plus_api_token_valid": False}
        )
    except Exception:
        logger.warning("Could not mark Crossref token invalid", exc_info=True)


def reset_token_validity() -> None:
    """Record that Crossref confirmed the stored token."""
    from coda.apps.preferences.models import GlobalPreferences

    GlobalPreferences.objects.update_or_create(defaults={"crossref_plus_api_token_valid": True})

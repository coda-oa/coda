"""Crossref Metadata Plus access: token verification and status.

Service layer for the preferences app: knows how to talk to Crossref with
the polite/Plus credentials from :class:`CrossrefPoliteness`, and how to
translate an HTTP response into a verification verdict. No Django form or
template knowledge lives here.
"""

from typing import Literal

import httpx

from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.fundingrequest.services.doi_import.doi_client._crossref._politeness import (
    CrossrefPoliteness,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client._crossref._token_validity import (
    AUTH_REJECT_STATUSES,
    mark_token_invalid,
    reset_token_validity,
)

CrossrefVerificationStatus = Literal["verified", "unverified", "rejected"]


def verify_plus_token(token: str, timeout: int = 5) -> tuple[int | None, dict[str, str]]:
    """Verify a Crossref Metadata Plus token against the documented endpoint.

    Performs ``GET https://api.crossref.org/works`` with the token sent as
    ``Crossref-Plus-API-Token: Bearer <key>``. A HEAD request is not an
    option: the endpoint answers 405 to HEAD regardless of auth.

    Returns ``(status, headers)``: the HTTP status code, or ``None`` when
    Crossref was unreachable (network error, timeout). *headers* carries the
    rate-limit and pool information from the response. ``x-api-pool`` is not
    officially documented; observed live values: ``public-array`` without a
    token, ``plus-array`` when a Plus token header is present, whether or
    not the key is valid; validity is judged by the HTTP status.
    """
    url = "https://api.crossref.org/works"
    auth_headers = CrossrefPoliteness(plus_token=token).headers()
    try:
        response = httpx.get(url, headers=auth_headers, timeout=timeout)
    except httpx.HTTPError:
        return None, {}

    return response.status_code, dict(response.headers)


def check_stored_token() -> tuple[CrossrefVerificationStatus, str, bool]:
    """Verify the token currently stored in the global preferences.

    Returns a ``(status, message, has_token)`` triple for display purposes:

    - ``"verified"``: Crossref accepted the token (HTTP 200, Plus pool).
    - ``"rejected"``: Crossref answered but refused the token (e.g. expired).
    - ``"unverified"``: no token configured, or Crossref unreachable.
    - ``has_token``: whether a token is stored at all. "unverified" covers
      both "none configured" and "Crossref unreachable", so consumers need
      this to decide whether showing a re-check button makes sense.

    Never raises on transport errors; verification is advisory. Reads the
    preferences row once, so status and ``has_token`` are consistent.
    """
    prefs, _ = GlobalPreferences.objects.get_or_create()
    token = prefs.crossref_plus_api_token
    if not token:
        return "unverified", "No key is saved. Requests to Crossref work, just more slowly.", False

    status, headers = verify_plus_token(token)
    if status is None:
        return (
            "unverified",
            "Could not reach Crossref to check the key. It is saved, but its validity is unknown.",
            True,
        )
    if status in AUTH_REJECT_STATUSES:
        mark_token_invalid()
        return (
            "rejected",
            f"Crossref no longer accepts the saved key (error {status}). Re-enter it below.",
            True,
        )
    if status != 200:
        # Transient problem (rate limit, outage): do not trust the verdict.
        return (
            "unverified",
            f"Crossref answered with error {status}; the key's validity is unknown.",
            True,
        )
    if not headers.get("x-api-pool", "").startswith("plus"):
        return (
            "unverified",
            "Crossref accepted the key, but could not confirm the faster access it should provide.",
            True,
        )

    reset_token_validity()
    rate_limit = headers.get("x-rate-limit-limit")
    interval = headers.get("x-rate-limit-interval")
    return (
        "verified",
        f"Key works: {rate_limit} requests per {interval} allowed.",
        True,
    )

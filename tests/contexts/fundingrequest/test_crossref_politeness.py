"""Tests for Crossref politeness credentials.

Seams:
- CrossrefPoliteness — pure value object, direct construction
- crossref.fetch_publication / fetch_publications_batch — FakeHttpxClient
  injected via the http_client parameter, asserting outgoing params/headers
"""

from typing import Any

import httpx
import pytest

from coda.contexts.fundingrequest.services.doi_import.doi_client import crossref
from coda.contexts.fundingrequest.services.doi_import.doi_client._crossref._politeness import (
    CrossrefPoliteness,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client.errors import DOIFetchError
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr


class RecordingClient:
    """Records constructor kwargs of every .get() call and returns a minimal response."""

    def __init__(self, json_data: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._json_data = json_data or {}

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        return _FakeResponse(self._json_data)


class _FakeResponse:
    def __init__(self, json_data: dict[str, Any]) -> None:
        self._json_data = json_data

    def raise_for_status(self) -> "_FakeResponse":
        return self

    def json(self) -> dict[str, Any]:
        return self._json_data


def test__politeness__public_tier__no_params_no_auth_headers() -> None:
    politeness = CrossrefPoliteness()
    assert politeness.query_params() == {}
    assert politeness.headers() == {}
    assert politeness.is_plus is False


def test__politeness__polite_tier__mailto_param_and_user_agent() -> None:
    politeness = CrossrefPoliteness(email=NonEmptyStr("contact@example.org"))
    assert politeness.query_params() == {"mailto": "contact@example.org"}
    headers = politeness.headers()
    assert "User-Agent" in headers
    assert "contact@example.org" in headers["User-Agent"]
    assert headers["User-Agent"].startswith("coda/")
    assert "Crossref-Plus-API-Token" not in headers


def test__politeness__plus_tier__token_in_documented_header() -> None:
    politeness = CrossrefPoliteness(
        email=NonEmptyStr("contact@example.org"), plus_token="secret-token"
    )
    headers = politeness.headers()
    assert headers["Crossref-Plus-API-Token"] == "Bearer secret-token"
    assert "crossref-api-key" not in headers


def test__politeness__blank_email_or_token__rejected() -> None:
    with pytest.raises(ValueError):
        CrossrefPoliteness(email=NonEmptyStr("   "))
    with pytest.raises(ValueError):
        CrossrefPoliteness(plus_token="  ")


def test__fetch_publication__with_politeness__sends_mailto_and_headers() -> None:
    politeness = CrossrefPoliteness(email=NonEmptyStr("contact@example.org"), plus_token="tok")
    client = RecordingClient(json_data={"message": {}})

    crossref.fetch_publication(Doi("10.1234/example"), politeness=politeness, http_client=client)

    call = client.calls[0]
    assert call["params"]["mailto"] == "contact@example.org"
    assert call["headers"]["Crossref-Plus-API-Token"] == "Bearer tok"
    assert "contact@example.org" in call["headers"]["User-Agent"]


def test__fetch_publication__without_politeness__sends_no_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "coda.apps.preferences.models.GlobalPreferences.get_crossref_politeness",
        classmethod(lambda cls: CrossrefPoliteness()),
    )
    client = RecordingClient(json_data={"message": {}})

    crossref.fetch_publication(Doi("10.1234/example"), http_client=client)

    call = client.calls[0]
    assert "mailto" not in call["params"]
    assert call["headers"] == {}


def test__fetch_publication__without_politeness__resolves_from_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "coda.apps.preferences.models.GlobalPreferences.get_crossref_politeness",
        classmethod(lambda cls: CrossrefPoliteness(email=NonEmptyStr("prefs@example.org"))),
    )
    client = RecordingClient(json_data={"message": {}})

    crossref.fetch_publication(Doi("10.1234/example"), http_client=client)

    call = client.calls[0]
    assert call["params"]["mailto"] == "prefs@example.org"


def test__fetch_publications_batch__with_politeness__sends_mailto_and_headers() -> None:
    politeness = CrossrefPoliteness(email=NonEmptyStr("contact@example.org"), plus_token="tok")
    client = RecordingClient(json_data={"message": {"items": [], "next-cursor": None}})

    crossref.fetch_publications_batch(
        [Doi("10.1234/a"), Doi("10.1234/b")],
        politeness=politeness,
        http_client=client,
    )

    call = client.calls[0]
    assert call["params"]["mailto"] == "contact@example.org"
    assert call["params"]["filter"] == "doi:10.1234/a,doi:10.1234/b"
    assert call["headers"]["Crossref-Plus-API-Token"] == "Bearer tok"


@pytest.mark.django_db
def test__fetch_publication__rejected_key__marks_invalid_and_stops_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First fetch with a rejected key marks it invalid; later requests go out without it."""
    from coda.apps.preferences.models import GlobalPreferences
    from coda.contexts.fundingrequest.services.doi_import.doi_client._crossref import (
        _token_validity,
    )

    GlobalPreferences.objects.create(
        crossref_plus_api_token="expired", crossref_plus_api_token_valid=True
    )
    rejection = httpx.HTTPStatusError(
        "401", request=httpx.Request("GET", "https://x"), response=httpx.Response(401)
    )
    client = RecordingClient()
    client.get = lambda url, **kwargs: (_ for _ in ()).throw(rejection)  # type: ignore[method-assign]

    with pytest.raises(DOIFetchError):
        crossref.fetch_publication(Doi("10.1234/example"), http_client=client)

    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is False

    # Subsequent fetches omit the token header entirely.
    recorder = RecordingClient(json_data={"message": {}})
    crossref.fetch_publication(Doi("10.1234/example"), http_client=recorder)
    assert "Crossref-Plus-API-Token" not in recorder.calls[0]["headers"]
    assert _token_validity.is_token_marked_invalid() is True


@pytest.mark.django_db
def test__fetch_publications_batch__rejected_key__marks_invalid() -> None:
    """A 401 on the batch path also trips the validity flag."""
    from coda.apps.preferences.models import GlobalPreferences

    GlobalPreferences.objects.create(
        crossref_plus_api_token="expired", crossref_plus_api_token_valid=True
    )
    rejection = httpx.HTTPStatusError(
        "401", request=httpx.Request("GET", "https://x"), response=httpx.Response(401)
    )
    client = RecordingClient()
    client.get = lambda url, **kwargs: (_ for _ in ()).throw(rejection)  # type: ignore[method-assign]

    results = crossref.fetch_publications_batch(
        [Doi("10.1234/a"), Doi("10.1234/b")], http_client=client
    )
    assert all(isinstance(e, DOIFetchError) for e in results.values())
    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is False


@pytest.mark.django_db
def test__fetch_publication__403_rejection__also_marks_invalid() -> None:
    """AUTH_REJECT_STATUSES covers 403, not just 401."""
    from coda.apps.preferences.models import GlobalPreferences

    GlobalPreferences.objects.create(
        crossref_plus_api_token="forbidden", crossref_plus_api_token_valid=True
    )
    rejection = httpx.HTTPStatusError(
        "403", request=httpx.Request("GET", "https://x"), response=httpx.Response(403)
    )
    client = RecordingClient()
    client.get = lambda url, **kwargs: (_ for _ in ()).throw(rejection)  # type: ignore[method-assign]

    with pytest.raises(DOIFetchError):
        crossref.fetch_publication(Doi("10.1234/example"), http_client=client)

    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is False

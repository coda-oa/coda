from django.test import Client
import pytest
from django.urls import reverse

from tests.apps._doubles import InMemoryVersionInfoProvider


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav_template__loads_banner_via_htmx(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    provider = InMemoryVersionInfoProvider()
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("home"))

    assert 'hx-get="' in response.content.decode()
    assert "check-update" in response.content.decode()


@pytest.mark.django_db
def test__check_update_view__returns_empty_when_no_update(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.update_info = {"update_available": False}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("check_update"))

    assert "update-banner" not in response.content.decode()


@pytest.mark.django_db
def test__check_update_view__returns_banner_when_update_available(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.branch = "develop"
    provider.update_info = {"update_available": True, "latest_commit": "abc123"}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("check_update"))

    assert "update-banner" in response.content.decode()
    assert "develop" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav_template__displays_version(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.version = "2026.01"
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("home"))

    assert "Version: 2026.01" in response.content.decode()

from django.test import Client
import pytest
from django.urls import reverse

from tests.apps._doubles import InMemoryVersionInfoProvider


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav_template__given_update_available__renders_banner(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.update_info = {"update_available": True, "latest_commit": "abc123"}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("home"))

    assert "update-banner" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav_template__given_no_update__hides_banner(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    provider = InMemoryVersionInfoProvider()
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("home"))

    assert "update-banner" not in response.content.decode()


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

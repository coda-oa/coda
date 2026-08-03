from collections.abc import Generator

import pytest
from django.http import HttpRequest
from django.test import RequestFactory, override_settings

from coda.apps.context_processors import demo_context, version_context
from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView
from tests.apps._doubles import InMemoryVersionInfoProvider
from coda.contexts.fundingrequest.services.doi_import.doi_client import (
    InMemoryDOIMetadataClient,
    crossref,
)


@pytest.fixture
def request_factory() -> RequestFactory:
    return RequestFactory()


@pytest.fixture
def in_memory_client() -> InMemoryDOIMetadataClient:
    client = InMemoryDOIMetadataClient()
    client.data["10.1234/demo.one"] = None  # type: ignore[assignment]
    client.data["10.1234/demo.two"] = None  # type: ignore[assignment]
    return client


@pytest.fixture(autouse=True)
def restore_doi_client() -> Generator[None]:
    yield
    DOIImportInputView.doi_client = crossref


def test__demo_context__when_demo_mode_false__returns_empty_dict(
    request_factory: RequestFactory,
    in_memory_client: InMemoryDOIMetadataClient,
) -> None:
    DOIImportInputView.doi_client = in_memory_client
    request = request_factory.get("/")

    with override_settings(CODA_DEMO_MODE=False):
        result = demo_context(request)

    assert result == {}


def test__demo_context__when_demo_mode_true_and_in_memory_client__returns_demo_dois(
    request_factory: RequestFactory,
    in_memory_client: InMemoryDOIMetadataClient,
) -> None:
    DOIImportInputView.doi_client = in_memory_client
    request = request_factory.get("/")

    with override_settings(CODA_DEMO_MODE=True):
        result = demo_context(request)

    assert set(result["demo_dois"]) == {"10.1234/demo.one", "10.1234/demo.two"}


def test__demo_context__when_demo_mode_true_but_crossref_client__returns_empty_dict(
    request_factory: RequestFactory,
) -> None:
    DOIImportInputView.doi_client = crossref
    request = request_factory.get("/")

    with override_settings(CODA_DEMO_MODE=True):
        result = demo_context(request)

    assert result == {}


def test__version_context__includes_update_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.branch = "develop"
    provider.version = "abc123"
    provider.update_info = {"update_available": True}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["coda_version"] == "abc123"
    assert ctx["update_available"] is True
    assert ctx["current_branch"] == "develop"
    assert ctx["github_url"] == "https://github.com/coda-oa/coda/tree/develop"


def test__version_context__with_tag__uses_release_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.branch = "stable"
    provider.version = "2026.01"
    provider.version_tag = "2026.01"
    provider.update_info = {"update_available": True}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["github_url"] == "https://github.com/coda-oa/coda/releases/tag/2026.01"


def test__version_context__without_tag__uses_branch_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = InMemoryVersionInfoProvider()
    provider.branch = "develop"
    provider.version = "abc1234"
    provider.version_tag = None
    provider.update_info = {"update_available": True}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["github_url"] == "https://github.com/coda-oa/coda/tree/develop"

from collections.abc import Generator

import pytest
from django.http import HttpRequest
from django.test import RequestFactory, override_settings

from coda.apps import version as version_module
from coda.apps.context_processors import demo_context, version_context
from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView
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


def test__version_context__includes_version_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        version_module,
        "_git",
        lambda args: (
            "develop"
            if args == ("rev-parse", "--abbrev-ref", "HEAD")
            else "abc123"
            if args == ("rev-parse", "--short", "HEAD")
            else None
        ),
    )
    monkeypatch.setattr(version_module, "_baked_file", lambda name: None)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["coda_version"] == "abc123"
    assert ctx["current_branch"] == "develop"
    assert ctx["github_url"] == "https://github.com/coda-oa/coda/tree/develop"


def test__version_context__update_available_is_false_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(version_module, "_git", lambda args: None)
    monkeypatch.setattr(version_module, "_baked_file", lambda name: None)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["update_available"] is False


def test__version_context__with_tag__uses_release_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        version_module, "_git", lambda args: "2026.01" if args[0] == "describe" else None
    )
    monkeypatch.setattr(version_module, "_baked_file", lambda name: None)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["github_url"] == "https://github.com/coda-oa/coda/releases/tag/2026.01"


def test__version_context__without_tag__uses_branch_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        version_module,
        "_git",
        lambda args: "develop" if args == ("rev-parse", "--abbrev-ref", "HEAD") else None,
    )
    monkeypatch.setattr(version_module, "_baked_file", lambda name: None)

    request = HttpRequest()
    ctx = version_context(request)

    assert ctx["github_url"] == "https://github.com/coda-oa/coda/tree/develop"

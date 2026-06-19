from collections.abc import Generator

import pytest
from django.test import RequestFactory, override_settings

from coda.apps.context_processors import demo_context
from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView
from coda.contexts.publication.services.doi_client import InMemoryDOIMetadataClient, crossref


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

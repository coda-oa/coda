from collections.abc import Generator

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView
from coda.contexts.publication.services.doi_client import InMemoryDOIMetadataClient, crossref
from coda.domain.publication.links import Doi


@pytest.fixture(autouse=True)
def restore_doi_client() -> Generator[None]:
    yield
    DOIImportInputView.doi_client = crossref


@pytest.fixture
def demo_client() -> InMemoryDOIMetadataClient:
    client = InMemoryDOIMetadataClient()
    client.data[str(Doi("10.1038/s41586-020-2649-2"))] = None  # type: ignore[assignment]
    client.data[str(Doi("10.1371/journal.pmed.0020124"))] = None  # type: ignore[assignment]
    return client


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__doi_input_page__when_demo_mode__shows_demo_hint(
    client: Client,
    demo_client: InMemoryDOIMetadataClient,
) -> None:
    DOIImportInputView.doi_client = demo_client

    with override_settings(CODA_DEMO_MODE=True):
        response = client.get(reverse("fundingrequests:doi_import_input"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "demo" in content.lower()
    assert "10.1038/s41586-020-2649-2" in content
    assert "10.1371/journal.pmed.0020124" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__doi_input_page__when_not_demo_mode__no_demo_hint(
    client: Client,
) -> None:
    with override_settings(CODA_DEMO_MODE=False):
        response = client.get(reverse("fundingrequests:doi_import_input"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Demo mode" not in content

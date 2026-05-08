from collections.abc import Generator

import pytest
from django.test import override_settings

from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
)
from coda.contexts.publication.services.doi_client import CrossrefDoiClient
from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient


def _reload_app() -> None:
    """Re-run AppConfig.ready() to apply settings change."""
    from django.apps import apps

    config = apps.get_app_config("fundingrequests")
    config.ready()


@pytest.fixture(autouse=True)
def restore_doi_client() -> Generator[None]:
    """Restore the original CrossrefDoiClient after each test to prevent leaking."""
    yield
    client = CrossrefDoiClient()
    DOIImportInputView.doi_client = client
    DOIPreviewDetailView.doi_client = client
    DOIPreviewSaveView.doi_client = client


@pytest.mark.django_db
def test__demo_mode__when_coda_demo_mode_true__wires_in_memory_client() -> None:
    with override_settings(CODA_DEMO_MODE=True):
        _reload_app()
        assert isinstance(DOIImportInputView.doi_client, InMemoryDOIMetadataClient)
        assert isinstance(DOIPreviewDetailView.doi_client, InMemoryDOIMetadataClient)
        assert isinstance(DOIPreviewSaveView.doi_client, InMemoryDOIMetadataClient)


@pytest.mark.django_db
def test__demo_mode__when_coda_demo_mode_false__does_not_swap_client() -> None:
    with override_settings(CODA_DEMO_MODE=False):
        _reload_app()
        assert isinstance(DOIImportInputView.doi_client, CrossrefDoiClient)
        assert isinstance(DOIPreviewDetailView.doi_client, CrossrefDoiClient)
        assert isinstance(DOIPreviewSaveView.doi_client, CrossrefDoiClient)

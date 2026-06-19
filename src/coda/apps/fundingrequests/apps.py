from django.apps import AppConfig


class FundingrequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coda.apps.fundingrequests"

    def ready(self) -> None:
        from django.conf import settings

        if getattr(settings, "CODA_DEMO_MODE", False):
            from pathlib import Path

            from coda.apps.fundingrequests.views.doi_preview import (
                DOIImportInputView,
                DOIPreviewDetailView,
                DOIPreviewSaveView,
            )
            from coda.contexts.publication.services.doi_client import InMemoryDOIMetadataClient

            client = InMemoryDOIMetadataClient.from_json(
                Path(settings.BASE_DIR) / "config/demo/fixtures/demo_dois.json"
            )
            DOIImportInputView.doi_client = client
            DOIPreviewDetailView.doi_client = client
            DOIPreviewSaveView.doi_client = client

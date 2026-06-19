from typing import Any

from django.http import HttpRequest

from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView
from coda.contexts.publication.services.doi_client import InMemoryDOIMetadataClient


def demo_context(request: HttpRequest) -> dict[str, Any]:
    """Inject demo DOI list into template context when CODA_DEMO_MODE is active.

    Returns ``{"demo_dois": [...]}`` when demo mode is on and the DOI input view
    has been wired with an InMemoryDOIMetadataClient (via AppConfig.ready()).
    Returns an empty dict otherwise, so no template changes are needed in
    production mode.
    """
    from django.conf import settings

    if not getattr(settings, "CODA_DEMO_MODE", False):
        return {}

    client = DOIImportInputView.doi_client
    if not isinstance(client, InMemoryDOIMetadataClient):
        return {}

    return {"demo_dois": list(client.data.keys())}

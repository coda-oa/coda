from typing import Any

from django.http import HttpRequest

from coda.apps.fundingrequests.views.doi_preview import DOIImportInputView
from coda.contexts.fundingrequest.services.doi_import.doi_client import InMemoryDOIMetadataClient

from coda.apps.version import get_branch, get_repo, get_version, get_version_tag


def version_context(request: HttpRequest) -> dict[str, Any]:
    version = get_version()
    branch = get_branch()
    tag = get_version_tag()
    repo = get_repo()
    if tag:
        github_url = f"https://github.com/{repo}/releases/tag/{tag}"
    else:
        github_url = f"https://github.com/{repo}/tree/{branch}"
    return {
        "coda_version": version,
        "update_available": False,
        "current_branch": branch,
        "github_url": github_url,
    }


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

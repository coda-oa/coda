from collections.abc import Generator

import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
    DeleteFunding,
)
from coda.contexts.publication.services.doi_client import crossref
from tests.contexts.publication.fixtures.sample_metadata import ArticleScenario
from tests.fundingrequests.test_doi_import_preview import get_session_key, submit_for_preview


@pytest.fixture
def scenario() -> Generator[ArticleScenario]:
    """Inject fake DOI client into views via dependency injection."""
    scenario = ArticleScenario()
    DOIImportInputView.doi_client = scenario.client
    DOIPreviewDetailView.doi_client = scenario.client
    DOIPreviewSaveView.doi_client = scenario.client

    yield scenario

    DOIImportInputView.doi_client = crossref
    DOIPreviewDetailView.doi_client = crossref
    DOIPreviewSaveView.doi_client = crossref


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__previewing_doi_import_with_funding__shows_funding_on_preview_page(
    client: Client, scenario: ArticleScenario
) -> None:
    scenario = scenario.with_funding([("BMBF", "Some project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    preview_url = response["Location"]

    preview_response = client.get(preview_url)

    assert "BMBF" in preview_response.content.decode()
    assert "Some project" in preview_response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__previewing_doi_import_with_funding__delete_funding_entry__funding_is_gone(
    client: Client, scenario: ArticleScenario
) -> None:
    scenario = scenario.with_funding([("BMBF", "Some project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    delete_funding(client, key, DeleteFunding(funder="BMBF", project_id="Some project"))

    preview_url = response["Location"]
    preview = client.get(preview_url)
    assert "BMBF" not in preview.content.decode()
    assert "Some project" not in preview.content.decode()


def delete_funding(client: Client, key: str, funding: DeleteFunding) -> None:
    client.post(
        reverse("fundingrequests:doi_preview_delete_funding", kwargs={"session_key": key}),
        formdata.map_to_dict(funding),
    )

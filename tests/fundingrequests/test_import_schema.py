import json

import pytest
from django.test import Client
from django.urls import reverse

from coda.contexts.fundingrequest.dto.import_dtos import FundingRequestImportListDto

pytestmark = pytest.mark.django_db


@pytest.fixture
def schema_url() -> str:
    return reverse("fundingrequests:import_schema")


@pytest.fixture
def download_url() -> str:
    return reverse("fundingrequests:import_schema_download")


def test_schema_fragment_returns_schema(logged_in: None, client: Client, schema_url: str) -> None:
    response = client.get(schema_url)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    body = response.content.decode()
    assert "&quot;requests&quot;" in body
    assert "&quot;$defs&quot;" in body


def test_schema_download_returns_json_file(
    logged_in: None, client: Client, download_url: str
) -> None:
    response = client.get(download_url)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Content-Disposition"] == (
        'attachment; filename="fundingrequest_import_schema.json"'
    )
    assert json.loads(response.content) == FundingRequestImportListDto.model_json_schema()


def test_schema_endpoints_require_login(client: Client, schema_url: str, download_url: str) -> None:
    for url in (schema_url, download_url):
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response["Location"]


def test_import_page_links_schema_and_download(logged_in: None, client: Client) -> None:
    response = client.get(reverse("fundingrequests:import"))

    assert response.status_code == 200
    html = response.content.decode()
    assert 'hx-get="' + reverse("fundingrequests:import_schema") + '"' in html
    assert reverse("fundingrequests:import_schema_download") in html
    assert "<summary" in html

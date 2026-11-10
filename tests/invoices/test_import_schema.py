import json

import pytest
from django.test import Client
from django.urls import reverse

from coda.contexts.finance.dto.import_dtos import InvoiceListImportDto

pytestmark = pytest.mark.django_db


@pytest.fixture
def schema_url() -> str:
    return reverse("invoices:import_schema")


@pytest.fixture
def download_url() -> str:
    return reverse("invoices:import_schema_download")


def test_schema_fragment_returns_schema(logged_in: None, client: Client, schema_url: str) -> None:
    response = client.get(schema_url)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    body = response.content.decode()
    assert "&quot;invoices&quot;" in body
    assert "&quot;$defs&quot;" in body


def test_schema_download_returns_json_file(
    logged_in: None, client: Client, download_url: str
) -> None:
    response = client.get(download_url)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Content-Disposition"] == 'attachment; filename="invoice_import_schema.json"'
    assert json.loads(response.content) == InvoiceListImportDto.model_json_schema()


def test_schema_endpoints_require_login(client: Client, schema_url: str, download_url: str) -> None:
    for url in (schema_url, download_url):
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response["Location"]


def test_import_page_links_schema_and_download(logged_in: None, client: Client) -> None:
    response = client.get(reverse("invoices:import"))

    assert response.status_code == 200
    html = response.content.decode()
    assert 'hx-get="' + reverse("invoices:import_schema") + '"' in html
    assert reverse("invoices:import_schema_download") in html
    assert "<summary" in html


def test_post_to_schema_endpoints_is_rejected(
    logged_in: None, client: Client, schema_url: str, download_url: str
) -> None:
    for url in (schema_url, download_url):
        response = client.post(url)
        assert response.status_code == 405

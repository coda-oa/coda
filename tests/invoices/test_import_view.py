import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        (b"{}", "invoices: Field required"),
        (b'{"invoices": null}', "invoices: Input should be a valid list"),
        (b'{"invoices": "not-a-list"}', "invoices: Input should be a valid list"),
        (b"[]", "Import file must contain a JSON object"),
        (b'{"invoices": ', "Invalid JSON"),
    ],
)
def test__invalid_import_document__shows_validation_message(
    logged_in: None, client: Client, content: bytes, expected_message: str
) -> None:
    upload = SimpleUploadedFile("invoices.json", content, content_type="application/json")

    response = client.post(reverse("invoices:import"), {"import_file": upload})

    assert response.status_code == 200
    assert expected_message in response.content.decode()

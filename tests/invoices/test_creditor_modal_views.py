import re

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.invoices.models import Creditor


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__click_on_new_creditor_from_invoice__returns_modal_with_creditor_form_and_correct_context(
    client: Client,
) -> None:
    response = client.get(reverse("invoices:creditor_create_modal"))

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["entity_name"] == "Creditor"
    assert response.context["entity_create_url"] == "invoices:creditor_create_modal_submit"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_creditor_entered__click_create_button__creates_creditor_and_returns_success_template(
    client: Client,
) -> None:
    creditor_name = "Acme Corporation"

    response = client.post(
        reverse("invoices:creditor_create_modal_submit"),
        {"name": creditor_name},
    )

    assert Creditor.objects.filter(name=creditor_name).exists()
    creditor = Creditor.objects.get(name=creditor_name)

    assert response.status_code == 200
    assert "invoices/partials/creditor_create_success.html" in [t.name for t in response.templates]
    assert response.context["creditors"].filter(pk=creditor.pk).exists()
    assert response.context["selected_creditor_id"] == creditor.id

    content = response.content.decode()
    assert 'id="entity-creation-modal-wrapper" hx-swap-oob="true"' in content
    assert 'id="creditor-select-wrapper" hx-swap-oob="true"' in content
    assert creditor_name in content
    assert re.search(rf'<li\s+value="{creditor.pk}"\s+selected>', content)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_creditor_entered__click_create_button__returns_modal_with_errors(
    client: Client,
) -> None:
    response = client.post(
        reverse("invoices:creditor_create_modal_submit"),
        {"name": ""},
    )

    assert Creditor.objects.count() == 0

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["form"].errors

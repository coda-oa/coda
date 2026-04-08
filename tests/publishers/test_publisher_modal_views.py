import re

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.publishers.models import Publisher


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__click_on_new_publisher_from_funding_request__returns_modal_with_publisher_form_and_correct_context(
    client: Client,
) -> None:
    response = client.get(reverse("publishing:publishers:create_modal"))

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["entity_name"] == "Publisher"
    assert (
        response.context["entity_create_url_path"] == "/publishing/publishers/create-modal/submit/"
    )
    assert response.context["modal_target_wrapper"] == "entity-creation-modal-wrapper"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_publisher_entered__click_create_button__creates_publisher_and_returns_success_template(
    client: Client,
) -> None:
    publisher_name = "Penguin Books"

    response = client.post(
        reverse("publishing:publishers:create_modal_submit"),
        {"name": publisher_name},
    )

    assert Publisher.objects.filter(name=publisher_name).exists()
    publisher = Publisher.objects.get(name=publisher_name)

    assert response.status_code == 200
    assert "publishers/partials/publisher_create_success.html" in [
        t.name for t in response.templates
    ]
    assert response.context["publisher"] == publisher

    content = response.content.decode()

    assert re.search(
        r'<div[^>]{0,200}id="entity-creation-modal-wrapper"[^>]{0,200}hx-swap-oob="true"', content
    )
    assert re.search(
        r'<div[^>]{0,200}id="publisher-search-results"[^>]{0,200}hx-swap-oob="true"', content
    )
    assert re.search(
        r'<div[^>]{0,200}id="publisher-name-wrapper"[^>]{0,200}hx-swap-oob="true"', content
    )
    assert publisher_name in content
    assert re.search(
        rf'<input\s+type="radio"\s+name="publisher"\s+value="{publisher.pk}"\s+checked>', content
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_publisher_entered__click_create_button__returns_modal_with_errors(
    client: Client,
) -> None:
    response = client.post(
        reverse("publishing:publishers:create_modal_submit"),
        {"name": ""},
    )

    assert Publisher.objects.count() == 0

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["form"].errors

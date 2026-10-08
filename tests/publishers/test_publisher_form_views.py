import pytest
from django.test import Client
from django.urls import reverse

from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_update__form_renders_with_current_name(client: Client) -> None:
    publisher = modelfactory.publisher(name="Acme Press")

    response = client.get(reverse("publishing:publishers:update", kwargs={"pk": publisher.pk}))

    assert response.status_code == 200
    assert response.context["form"].initial["name"] == "Acme Press"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_update__submit_renames_publisher(client: Client) -> None:
    publisher = modelfactory.publisher(name="Acme Press")

    response = client.post(
        reverse("publishing:publishers:update", kwargs={"pk": publisher.pk}),
        data={"name": "Acme Publishing"},
    )

    assert response.status_code == 302
    publisher.refresh_from_db()
    assert publisher.name == "Acme Publishing"

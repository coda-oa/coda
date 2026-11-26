import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse

from coda.apps.publishers.models import Publisher
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
    assert response["Location"] == reverse(
        "publishing:publishers:detail", kwargs={"pk": publisher.pk}
    )
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Publisher 'Acme Publishing' updated successfully."
    ]
    publisher.refresh_from_db()
    assert publisher.name == "Acme Publishing"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_create__redirects_to_detail_and_flashes_success(client: Client) -> None:
    response = client.post(
        reverse("publishing:publishers:create"),
        data={"name": "New Press"},
    )

    publisher = Publisher.objects.get(name="New Press")
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "publishing:publishers:detail", kwargs={"pk": publisher.pk}
    )
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Publisher created successfully."
    ]

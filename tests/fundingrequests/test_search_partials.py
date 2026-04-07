import pytest
from django.test import Client
from django.urls import reverse
from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_publisher__returns_publisher_name_in_row(client: Client) -> None:
    modelfactory.publisher(name="Springer Nature")

    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": "Springer"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Springer Nature" in content
    assert 'name="publisher"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_publisher__no_results__shows_no_results_message(client: Client) -> None:
    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": "nonexistent"},
    )

    assert response.status_code == 200
    assert "No results" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_publisher__returns_results_sorted_by_name(client: Client) -> None:
    modelfactory.publisher(name="Zebra Press")
    modelfactory.publisher(name="Alpha Press")

    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": "press"},
    )

    content = response.content.decode()
    assert content.index("Alpha Press") < content.index("Zebra Press")

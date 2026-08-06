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
@pytest.mark.parametrize(
    ("search_term",),
    [
        ("  Springer",),
        ("Springer  ",),
        ("  Springer  ",),
    ],
)
def test__find_publisher__leading_or_trailing_whitespace__still_found(
    client: Client, search_term: str
) -> None:
    modelfactory.publisher(name="Springer Nature")

    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": search_term},
    )

    assert response.status_code == 200
    assert "Springer Nature" in response.content.decode()


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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_journal__returns_journal_title_in_row(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer")
    modelfactory.journal(title="Nature", publisher_id=publisher.pk)

    response = client.post(
        reverse("fundingrequests:wizard_find_journal"),
        data={"journal_title": "Nature"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Nature" in content
    assert "Springer" in content
    assert 'name="journal"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_journal__no_results__shows_no_results_message(client: Client) -> None:
    response = client.post(
        reverse("fundingrequests:wizard_find_journal"),
        data={"journal_title": "nonexistent"},
    )

    assert response.status_code == 200
    assert "No results" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_journal__returns_results_sorted_by_title(client: Client) -> None:
    publisher = modelfactory.publisher()
    modelfactory.journal(title="Zebra Journal", publisher_id=publisher.pk)
    modelfactory.journal(title="Alpha Journal", publisher_id=publisher.pk)

    response = client.post(
        reverse("fundingrequests:wizard_find_journal"),
        data={"journal_title": "journal"},
    )

    content = response.content.decode()
    assert content.index("Alpha Journal") < content.index("Zebra Journal")

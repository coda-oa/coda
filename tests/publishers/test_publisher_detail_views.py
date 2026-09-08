import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.publishers.models import Publisher
from tests import modelfactory


def _detail_url(publisher: Publisher) -> str:
    return reverse("publishing:publishers:detail", kwargs={"pk": publisher.pk})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__shows_publisher_name(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")

    response = client.get(_detail_url(publisher))

    assert response.status_code == 200
    assert "Springer Nature" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__lists_own_journals(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")
    modelfactory.journal(publisher.pk, title="Springer Journal Of Testing")

    response = client.get(_detail_url(publisher))

    assert "Springer Journal Of Testing" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__excludes_journals_of_other_publishers(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")
    other_publisher = modelfactory.publisher(name="Elsevier")
    modelfactory.journal(publisher.pk, title="Springer Journal Of Testing")
    modelfactory.journal(other_publisher.pk, title="Elsevier Journal Of Impostors")

    response = client.get(_detail_url(publisher))
    content = response.content.decode()

    assert "Springer Journal Of Testing" in content
    assert "Elsevier Journal Of Impostors" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__empty_journal_list_shows_placeholder(client: Client) -> None:
    publisher = modelfactory.publisher(name="Lonely Publisher")

    response = client.get(_detail_url(publisher))

    assert "No journals to display." in response.content.decode()

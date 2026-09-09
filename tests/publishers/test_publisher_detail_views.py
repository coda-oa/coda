import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import FundingRequest
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


def _article_request(
    publisher: Publisher,
    title: str,
    journal_title: str = "Journal Of Publisher Metadata",
) -> FundingRequest:
    journal = modelfactory.journal(publisher.pk, title=journal_title)
    funding_request = modelfactory.fundingrequest(title=title)
    funding_request.publication.article_journal = journal
    funding_request.publication.save()
    return funding_request


def _monograph_request(publisher: Publisher, title: str) -> FundingRequest:
    funding_request = modelfactory.fundingrequest(title=title)
    funding_request.publication.article_journal = None
    funding_request.publication.monograph_publisher = publisher
    funding_request.publication.save()
    return funding_request


def _row(content: str, request_id: str) -> str:
    start = content.index(request_id)
    return content[content.rindex("<tr>", 0, start) : content.index("</tr>", start)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__lists_funding_requests_of_own_journal_articles(
    client: Client,
) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")
    funding_request = _article_request(publisher, "Testing Patterns")

    response = client.get(_detail_url(publisher))
    content = response.content.decode()

    assert funding_request.request_id in content
    assert "Testing Patterns" in _row(content, funding_request.request_id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__lists_funding_requests_of_own_monographs(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")
    funding_request = _monograph_request(publisher, "Monograph On Impostors")

    response = client.get(_detail_url(publisher))
    content = response.content.decode()

    assert funding_request.request_id in content
    assert "Monograph On Impostors" in _row(content, funding_request.request_id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__labels_journal_articles_as_article_type(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")
    article = _article_request(publisher, "Testing Patterns")
    monograph = _monograph_request(publisher, "Book Of Tests")

    response = client.get(_detail_url(publisher))
    content = response.content.decode()

    assert "Article" in _row(content, article.request_id)
    assert "Monograph" not in _row(content, article.request_id)
    assert "Monograph" in _row(content, monograph.request_id)
    assert "Article" not in _row(content, monograph.request_id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__excludes_funding_requests_of_other_publishers(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer Nature")
    other_publisher = modelfactory.publisher(name="Elsevier")
    foreign_article = _article_request(other_publisher, "Foreign Publication")
    foreign_monograph = _monograph_request(other_publisher, "Foreign Monograph")
    own = _article_request(publisher, "Own Publication")

    response = client.get(_detail_url(publisher))
    content = response.content.decode()

    assert own.request_id in content
    assert foreign_article.request_id not in content
    assert foreign_monograph.request_id not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_detail__no_funding_requests_shows_placeholder(client: Client) -> None:
    publisher = modelfactory.publisher(name="Lonely Publisher")

    response = client.get(_detail_url(publisher))

    assert "No related funding requests." in response.content.decode()

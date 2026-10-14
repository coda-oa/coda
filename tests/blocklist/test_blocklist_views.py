import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.blocklist.models import BlockList
from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_journal__journal_is_blocked(client: Client) -> None:
    blocklist = BlockList.objects.create()

    journal = modelfactory.journal()
    url = reverse("blocklist:block_journal", kwargs={"pk": journal.pk})

    response = client.post(url)

    assert response.status_code == 200
    assert blocklist.is_journal_blocked(journal)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__blocked_journal__unblock__journal_is_unblocked(client: Client) -> None:
    blocklist = BlockList.objects.create()

    journal = modelfactory.journal()
    blocklist.block_journal(journal, reason="MIRROR")

    url = reverse("blocklist:unblock_journal", kwargs={"pk": journal.pk})
    response = client.post(url)

    assert response.status_code == 200
    assert not blocklist.is_journal_blocked(journal)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_publisher__publisher_is_blocked_and_redirects_to_detail(
    client: Client,
) -> None:
    blocklist = BlockList.objects.create()

    publisher = modelfactory.publisher()
    url = reverse("blocklist:block_publisher", kwargs={"pk": publisher.pk})

    response = client.post(url)

    assert response.status_code == 200
    assert blocklist.is_publisher_blocked(publisher)
    assert response.headers["HX-Redirect"] == publisher.get_absolute_url()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_publisher__with_redirect_url__redirects_to_posted_url(client: Client) -> None:
    blocklist = BlockList.objects.create()

    publisher = modelfactory.publisher()
    url = reverse("blocklist:block_publisher", kwargs={"pk": publisher.pk})

    response = client.post(url, {"redirect_url": "/publishing/publishers/"})

    assert response.status_code == 200
    assert blocklist.is_publisher_blocked(publisher)
    assert response.headers["HX-Redirect"] == "/publishing/publishers/"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_publisher__redirects_to_current_htmx_url(client: Client) -> None:
    blocklist = BlockList.objects.create()

    publisher = modelfactory.publisher()
    url = reverse("blocklist:block_publisher", kwargs={"pk": publisher.pk})

    response = client.post(
        url, headers={"HX-Current-URL": "http://testserver/publishing/publishers/"}
    )

    assert response.status_code == 200
    assert blocklist.is_publisher_blocked(publisher)
    assert response.headers["HX-Redirect"] == "/publishing/publishers/"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_publisher__posted_url_wins_over_current_htmx_url(client: Client) -> None:
    blocklist = BlockList.objects.create()

    publisher = modelfactory.publisher()
    url = reverse("blocklist:block_publisher", kwargs={"pk": publisher.pk})

    response = client.post(
        url,
        {"redirect_url": "/publishing/publishers/"},
        headers={"HX-Current-URL": "http://testserver/somewhere/else/"},
    )

    assert response.status_code == 200
    assert blocklist.is_publisher_blocked(publisher)
    assert response.headers["HX-Redirect"] == "/publishing/publishers/"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__unblock_publisher__redirects_to_current_htmx_url(client: Client) -> None:
    blocklist = BlockList.objects.create()

    publisher = modelfactory.publisher()
    blocklist.block_publisher(publisher)
    url = reverse("blocklist:unblock_publisher", kwargs={"pk": publisher.pk})

    response = client.post(
        url, headers={"HX-Current-URL": "http://testserver/publishing/publishers/"}
    )

    assert response.status_code == 200
    assert not blocklist.is_publisher_blocked(publisher)
    assert response.headers["HX-Redirect"] == "/publishing/publishers/"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_journal__redirects_to_current_htmx_url(client: Client) -> None:
    blocklist = BlockList.objects.create()

    journal = modelfactory.journal()
    url = reverse("blocklist:block_journal", kwargs={"pk": journal.pk})

    response = client.post(
        url, headers={"HX-Current-URL": "http://testserver/publishing/journals/"}
    )

    assert response.status_code == 200
    assert blocklist.is_journal_blocked(journal)
    assert response.headers["HX-Redirect"] == "/publishing/journals/"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__block_journal__redirects_to_detail_by_default(client: Client) -> None:
    blocklist = BlockList.objects.create()

    journal = modelfactory.journal()
    url = reverse("blocklist:block_journal", kwargs={"pk": journal.pk})

    response = client.post(url)

    assert response.status_code == 200
    assert blocklist.is_journal_blocked(journal)
    assert response.headers["HX-Redirect"] == journal.get_absolute_url()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__unblock_journal__redirects_to_current_htmx_url(client: Client) -> None:
    blocklist = BlockList.objects.create()

    journal = modelfactory.journal()
    blocklist.block_journal(journal, reason="MIRROR")
    url = reverse("blocklist:unblock_journal", kwargs={"pk": journal.pk})

    response = client.post(
        url, headers={"HX-Current-URL": "http://testserver/publishing/journals/"}
    )

    assert response.status_code == 200
    assert not blocklist.is_journal_blocked(journal)
    assert response.headers["HX-Redirect"] == "/publishing/journals/"

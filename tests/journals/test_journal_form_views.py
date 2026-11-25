import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_journal__redirects_to_detail_and_flashes_success(client: Client) -> None:
    publisher = Publisher.objects.create(name="Test Publisher")

    response = client.post(
        reverse("publishing:journals:create"),
        {"title": "New Journal", "eissn": "1476-4687", "publisher": publisher.pk},
    )

    journal = Journal.objects.get(title="New Journal")
    assert response.status_code == 302
    assert response["Location"] == reverse("publishing:journals:detail", kwargs={"pk": journal.pk})
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Journal created successfully."
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_journal__redirects_to_detail_and_flashes_named_success(
    client: Client,
) -> None:
    publisher = Publisher.objects.create(name="Test Publisher")
    journal = Journal.objects.create(title="Old Journal", eissn="1476-4687", publisher=publisher)

    response = client.post(
        reverse("publishing:journals:update", kwargs={"pk": journal.pk}),
        {"title": "Renamed Journal", "eissn": "1476-4687", "publisher": publisher.pk},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("publishing:journals:detail", kwargs={"pk": journal.pk})
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Journal 'Renamed Journal' updated successfully."
    ]

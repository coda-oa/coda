from django.urls import reverse
import pytest
from django.test import Client

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

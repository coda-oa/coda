import pytest
from django.test import Client
from django.urls import reverse
from tests import modelfactory

from coda.apps.blocklist.models import BlockList


def _list_url() -> str:
    return reverse("publishing:journals:list")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__shows_block_button_for_unblocked_journal(client: Client) -> None:
    modelfactory.journal(title="Free Journal")

    response = client.get(_list_url())

    content = response.content.decode()
    assert "Free Journal" in content
    assert ">Block</button>" in content
    assert ">Unblock</button>" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__shows_unblock_button_for_blocked_journal(client: Client) -> None:
    blocked = modelfactory.journal(title="Blocked Journal")
    BlockList.objects.get().block_journal(blocked, reason="PREDATORY")

    response = client.get(_list_url())

    content = response.content.decode()
    assert "Blocked Journal" in content
    assert ">Unblock</button>" in content
    assert ">Block</button>" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__blocked_journal_unblocked_via_row_button(client: Client) -> None:
    blocked = modelfactory.journal(title="Blocked Journal")
    blocklist = BlockList.objects.get()
    blocklist.block_journal(blocked, reason="PREDATORY")

    client.post(reverse("blocklist:unblock_journal", kwargs={"pk": blocked.pk}))

    response = client.get(_list_url())

    content = response.content.decode()
    assert ">Block</button>" in content
    assert ">Unblock</button>" not in content

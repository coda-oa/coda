import pytest
from django.test import Client
from django.urls import reverse
from tests import modelfactory

from coda.apps.blocklist.models import BlockList


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__blocked_only_shows_only_blocked_journals(client: Client) -> None:
    blocked = modelfactory.journal(title="Blocked Journal")
    modelfactory.journal(title="Free Journal")
    BlockList.objects.get().block_journal(blocked, reason="PREDATORY")

    response = client.get(reverse("publishing:journals:list"), {"blocked_only": "on"})

    content = response.content.decode()
    assert "Blocked Journal" in content
    assert "Free Journal" not in content
    assert "Show blocked only" in content
    assert 'aria-checked="true"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__blocked_only_combines_with_search(client: Client) -> None:
    blocked_match = modelfactory.journal(title="Blocked Springer Journal")
    blocked_other = modelfactory.journal(title="Blocked Elsevier Journal")
    modelfactory.journal(title="Free Springer Journal")
    blocklist = BlockList.objects.get()
    blocklist.block_journal(blocked_match, reason="PREDATORY")
    blocklist.block_journal(blocked_other, reason="PREDATORY")

    response = client.get(
        reverse("publishing:journals:list"), {"blocked_only": "on", "query": "Springer"}
    )

    content = response.content.decode()
    assert "Blocked Springer Journal" in content
    assert "Blocked Elsevier Journal" not in content
    assert "Free Springer Journal" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__unblocked_by_default(client: Client) -> None:
    blocked = modelfactory.journal(title="Blocked Journal")
    modelfactory.journal(title="Free Journal")
    BlockList.objects.get().block_journal(blocked, reason="PREDATORY")

    response = client.get(reverse("publishing:journals:list"))

    content = response.content.decode()
    assert "Blocked Journal" in content
    assert "Free Journal" in content

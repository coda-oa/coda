import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from tests import modelfactory

from coda.apps.blocklist.models import BlockList
from coda.apps.journals.models import Journal


def _list_query_count(client: Client) -> int:
    with CaptureQueriesContext(connection) as context:
        response = client.get(reverse("publishing:journals:list"))
    assert response.status_code == 200
    return len(context.captured_queries)


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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list__query_count_does_not_grow_with_journal_count(
    client: Client,
) -> None:
    modelfactory.journal(title="Journal warmup")
    _list_query_count(client)  # bootstraps the BlockList singleton outside the measurement

    for index in range(12):
        modelfactory.journal(title=f"Journal {index}")
    count_with_many = _list_query_count(client)

    for index in range(12):
        Journal.objects.filter(title=f"Journal {index}").delete()
    modelfactory.journal(title="Journal single")
    count_with_one = _list_query_count(client)

    assert count_with_many == count_with_one

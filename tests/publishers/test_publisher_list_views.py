import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.blocklist.models import BlockList
from coda.apps.publishers.models import Publisher
from tests import modelfactory


def _list_query_count(client: Client) -> int:
    with CaptureQueriesContext(connection) as context:
        response = client.get(reverse("publishing:publishers:list"))
    assert response.status_code == 200
    return len(context.captured_queries)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_list__query_count_does_not_grow_with_publisher_count(
    client: Client,
) -> None:
    modelfactory.publisher(name="Publisher warmup")
    _list_query_count(client)  # bootstraps the BlockList singleton outside the measurement

    for index in range(12):
        modelfactory.publisher(name=f"Publisher {index}")
    count_with_many = _list_query_count(client)

    Publisher.objects.filter(name__startswith="Publisher ").delete()
    modelfactory.publisher(name="Publisher single")
    count_with_one = _list_query_count(client)

    assert count_with_many == count_with_one


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_list__blocked_only_shows_only_blocked_publishers(client: Client) -> None:
    blocked = modelfactory.publisher(name="Blocked Press")
    modelfactory.publisher(name="Free Press")
    BlockList.objects.get().block_publisher(blocked)

    response = client.get(reverse("publishing:publishers:list"), {"blocked_only": "on"})

    content = response.content.decode()
    assert "Blocked Press" in content
    assert "Free Press" not in content
    assert "Show blocked only" in content
    assert 'aria-checked="true"' in content
    assert 'hx-target="#entity-list-region"' in content
    assert 'hx-get="/publishing/publishers/"' in content
    assert 'hx-trigger="submit, change from:#id-blocked-only"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publisher_list__blocked_only_combines_with_search(client: Client) -> None:
    blocked_match = modelfactory.publisher(name="Blocked Springer")
    blocked_other = modelfactory.publisher(name="Blocked Elsevier")
    modelfactory.publisher(name="Free Springer")
    blocklist = BlockList.objects.get()
    blocklist.block_publisher(blocked_match)
    blocklist.block_publisher(blocked_other)

    response = client.get(
        reverse("publishing:publishers:list"), {"blocked_only": "on", "query": "Springer"}
    )

    content = response.content.decode()
    assert "Blocked Springer" in content
    assert "Blocked Elsevier" not in content
    assert "Free Springer" not in content

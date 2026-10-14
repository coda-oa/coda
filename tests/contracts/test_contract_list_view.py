import datetime

import pytest
from django.test import Client
from django.urls import reverse

from tests import modelfactory


def _create_contract(name: str, start: datetime.date | None, end: datetime.date | None) -> None:
    contract = modelfactory.contract()
    contract.name = name
    contract.start_date = start
    contract.end_date = end
    contract.save()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__hides_inactive_contracts_by_default(client: Client) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    _create_contract("Active Contract", today - datetime.timedelta(days=30), None)
    _create_contract(
        "Ended Contract", today - datetime.timedelta(days=60), today - datetime.timedelta(days=1)
    )
    _create_contract(
        "Future Contract", today + datetime.timedelta(days=1), today + datetime.timedelta(days=30)
    )

    response = client.get(reverse("contracts:list"))

    content = response.content.decode()
    assert "Active Contract" in content
    assert "Ended Contract" not in content
    assert "Future Contract" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__include_inactive_shows_all(client: Client) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    _create_contract("Active Contract", today - datetime.timedelta(days=30), None)
    _create_contract(
        "Ended Contract", today - datetime.timedelta(days=60), today - datetime.timedelta(days=1)
    )
    _create_contract(
        "Future Contract", today + datetime.timedelta(days=1), today + datetime.timedelta(days=30)
    )

    response = client.get(reverse("contracts:list"), {"include_inactive": "on"})

    content = response.content.decode()
    assert "Active Contract" in content
    assert "Ended Contract" in content
    assert "Future Contract" in content
    assert "Include inactive" in content
    assert 'aria-checked="true"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__inactive_filter_combines_with_search(client: Client) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    _create_contract(
        "Ended Springer", today - datetime.timedelta(days=60), today - datetime.timedelta(days=1)
    )
    _create_contract("Active Springer", today - datetime.timedelta(days=30), None)

    response = client.get(
        reverse("contracts:list"), {"include_inactive": "on", "query": "Springer"}
    )

    content = response.content.decode()
    assert "Ended Springer" in content
    assert "Active Springer" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__active_search_excludes_inactive_matches(client: Client) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    _create_contract(
        "Ended Springer", today - datetime.timedelta(days=60), today - datetime.timedelta(days=1)
    )
    _create_contract("Active Springer", today - datetime.timedelta(days=30), None)

    response = client.get(reverse("contracts:list"), {"query": "Springer"})

    content = response.content.decode()
    assert "Active Springer" in content
    assert "Ended Springer" not in content

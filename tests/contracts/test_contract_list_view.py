import datetime

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.contracts.models import ContractLink, ContractLinkType
from coda.apps.contracts.search import CONTRACT_SEARCH_FIELD_ALIASES
from tests import modelfactory


def _create_contract(name: str, start: datetime.date | None, end: datetime.date | None) -> None:
    contract = modelfactory.contract()
    contract.name = name
    contract.start_date = start
    contract.end_date = end
    contract.save()


def _add_link(contract: ContractModel, link_type: str, value: str) -> None:
    type_obj, _ = ContractLinkType.objects.get_or_create(name=link_type)
    ContractLink.objects.create(contract=contract, type=type_obj, value=value)


def _named_contract(name: str) -> ContractModel:
    contract = modelfactory.contract()
    contract.name = name
    contract.save()
    return contract


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__renders_search_prefix_helper(client: Client) -> None:
    response = client.get(reverse("contracts:list"))

    content = response.content.decode()
    assert 'aria-describedby="entity-filter-helper"' in content
    assert "Prefix term to search a specific field" in content
    assert f"<code>{', '.join(CONTRACT_SEARCH_FIELD_ALIASES)}</code>" in content


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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize("link_type", ["ESAC", "OAI", "EZB"])
def test__contract_list__search_matches_link_value_of_any_type(
    client: Client, link_type: str
) -> None:
    contract = _named_contract("Linked Contract")
    _add_link(contract, link_type, "unique-link-value")

    response = client.get(reverse("contracts:list"), {"query": "unique-link-value"})

    assert "Linked Contract" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize(
    ("matching_type", "prefix"),
    [("ESAC", "esac"), ("OAI", "oai"), ("EZB", "ezb")],
)
def test__contract_list__link_prefix_scopes_to_link_type(
    client: Client, matching_type: str, prefix: str
) -> None:
    matching = _named_contract("Matching Contract")
    other_type = next(t for t in ("ESAC", "OAI", "EZB") if t != matching_type)
    other = _named_contract("Other Contract")
    _add_link(matching, matching_type, "shared-link-value")
    _add_link(other, other_type, "shared-link-value")

    response = client.get(reverse("contracts:list"), {"query": f"{prefix}:shared-link-value"})

    content = response.content.decode()
    assert "Matching Contract" in content
    assert "Other Contract" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__mixed_prefixes__match_separate_link_rows(client: Client) -> None:
    matching = _named_contract("Matching Contract")
    _add_link(matching, "ESAC", "esac-mixed")
    _add_link(matching, "OAI", "oai-mixed")
    other = _named_contract("Other Contract")
    _add_link(other, "ESAC", "esac-mixed")
    _add_link(other, "OAI", "oai-other")

    response = client.get(reverse("contracts:list"), {"query": "esac:esac-mixed oai:oai-mixed"})

    content = response.content.decode()
    assert "Matching Contract" in content
    assert "Other Contract" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__matching_multiple_links__lists_contract_once(client: Client) -> None:
    contract = _named_contract("Duplicated Contract")
    _add_link(contract, "ESAC", "dupe-42")
    _add_link(contract, "OAI", "dupe-42")

    response = client.get(reverse("contracts:list"), {"query": "dupe-42"})

    assert [entity.name for entity in response.context["entities"]] == ["Duplicated Contract"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_list__orders_by_name(client: Client) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    _create_contract("Zulu Contract", today, None)
    _create_contract("Alpha Contract", today, None)

    response = client.get(reverse("contracts:list"))

    assert [entity.name for entity in response.context["entities"]] == [
        "Alpha Contract",
        "Zulu Contract",
    ]

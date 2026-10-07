"""Query-count regression guards for the fundingrequest list and detail pages.

The list page must not fetch contract publishers/journals per row: the mapped
domain Contract defers both M2M collections to first use (LazyCachedIterable
factory), and the only list-side consumers read period and billing. These
tests seed contracts on every row and pin the flat query curve plus a total
budget; a reintroduced per-row/per-contract fetch breaks the equality.
"""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.models import AttachedContract
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from tests import modelfactory

LIST_BUDGET = 16  # measured 14 (+2 slack) with labels + contract years on every row
DETAIL_BUDGET = 25  # measured 23 (+2 slack) with contracts, authors and labels


def _get(client: Client, url: str) -> tuple[int, str]:
    """GET url, returning (query_count, decoded_body)."""
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200
    return len(ctx.captured_queries), response.content.decode()


def _seed_request(contract: Contract, title: str) -> FundingRequest:
    fr = modelfactory.fundingrequest(title=title)
    label = label_create(f"Guard {title}", Color.from_rgb(1, 2, 3))
    label_attach(fr, label)
    AttachedContract.objects.create(
        publication=fr.publication, contract=contract, contract_year=2024
    )
    return fr


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize("url_name", ["fundingrequests:list", "fundingrequests:list_region"])
def test__list_page__query_count_is_flat_in_row_count(client: Client, url_name: str) -> None:
    url = reverse(url_name)
    contract = modelfactory.contract()
    _seed_request(contract, "Only row")

    _get(client, url)  # warmup: first request pays one-off middleware inserts
    small, body = _get(client, url)
    assert "Only row" in body  # guard against vacuous comparisons on an empty page
    assert small <= LIST_BUDGET

    for i in range(9):
        _seed_request(contract, f"Seeded row {i}")

    large, body = _get(client, url)
    for i in range(9):
        assert f"Seeded row {i}" in body  # all 10 rows (full page) are rendered
    assert large == small


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_page__query_count_is_flat_in_contract_count(client: Client) -> None:
    fr = _seed_request(modelfactory.contract(), "Growing contract set")
    url = reverse("fundingrequests:detail", kwargs={"pk": fr.pk})
    _get(client, url)  # warmup: first request pays one-off middleware inserts
    one, body = _get(client, url)
    assert "Growing contract set" in body
    assert one <= DETAIL_BUDGET

    contract_names = []
    for year in (2023, 2024, 2025):
        extra = modelfactory.contract()
        contract_names.append(extra.name)
        AttachedContract.objects.create(
            publication=fr.publication, contract=extra, contract_year=year
        )

    many, body = _get(client, url)
    for name in contract_names:
        assert name in body  # every attached contract is actually rendered
    assert many == one

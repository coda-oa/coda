"""Query-count regression guards for the invoice pages.

The real guard for the LazyCachedIterable fix is the repository mapping test
below: `repository.all()` maps every invoice through InvoiceDomainMapper and
the domain positions must never be consumed, so a regression to an eager
generator expression (which evaluates its outer iterable at creation) would
issue one positions SELECT per invoice.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.contracts.models import Contract
from coda.apps.invoices import repository as invoice_repository
from coda.apps.invoices.models import Invoice, Position
from coda.apps.publications.models import Publication
from tests import modelfactory

LIST_BUDGET = 14  # measured 11 (+3 slack) with six invoices carrying positions
DETAIL_BUDGET = 25  # measured 23 (+2 slack) with four positions; see note below


def _query_count(client: Client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200
    return len(ctx.captured_queries)


def _position(invoice: Invoice, publication: Publication, contract: Contract) -> Position:
    return Position.objects.create(
        description="OA fee",
        invoice=invoice,
        publication=publication,
        contract=contract,
        contract_year=2024,
        cost_amount=Decimal("100.00"),
        cost_currency="EUR",
        cost_type="read",
        tax_rate=Decimal("19.00"),
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__mapped_invoices__never_read_positions__costs_no_position_queries() -> None:
    contract = modelfactory.contract()
    publication = modelfactory.publication(title="Invoiced publication")
    for _ in range(5):
        invoice = modelfactory.invoice()
        _position(invoice, publication, contract)
        _position(invoice, publication, contract)

    with CaptureQueriesContext(connection) as ctx:
        invoices = list(invoice_repository.all())  # maps every invoice via InvoiceDomainMapper

    assert len(invoices) == 5
    position_queries = [q for q in ctx.captured_queries if "invoices_position" in q["sql"]]
    assert position_queries == []  # deferred positions: mapping must not fetch them


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_list__query_count_is_flat_in_invoice_count(client: Client) -> None:
    contract = modelfactory.contract()
    publication = modelfactory.publication(title="Invoiced publication")

    invoice = modelfactory.invoice()
    _position(invoice, publication, contract)

    url = reverse("invoices:list")
    _query_count(client, url)  # warmup: first request pays one-off middleware inserts
    small = _query_count(client, url)
    assert small <= LIST_BUDGET

    for _ in range(4):
        invoice = modelfactory.invoice()
        _position(invoice, publication, contract)
        _position(invoice, publication, contract)

    large = _query_count(client, url)
    assert large == small


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_detail__query_count_within_budget(client: Client) -> None:
    contract = modelfactory.contract()
    publication = modelfactory.publication(title="Invoiced publication")
    invoice = modelfactory.invoice()
    for _ in range(4):
        _position(invoice, publication, contract)

    url = reverse("invoices:detail", args=[invoice.pk])
    _query_count(client, url)  # warmup: first request pays one-off middleware inserts
    count = _query_count(client, url)

    # The remaining ~2-3 queries/position slope is a pre-existing N+1 in the
    # currency-conversion view-model path: invoice_parser._contract.to_itemdto
    # re-fetches each position's contract via contract_repository.get_by_id
    # even though it is already loaded (stack-verified). The domain mapping
    # itself is query-free (guarded by the repository test above).
    assert count <= DETAIL_BUDGET

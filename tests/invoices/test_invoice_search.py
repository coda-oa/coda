from collections.abc import Callable
from typing import cast

import pytest
from django.urls import reverse

from coda.apps.invoices import repository as invoice_repository
from coda.apps.invoices.models import Creditor
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import CreditorId, Invoice, InvoiceId
from coda.domain.invoice_list_item import InvoiceListItem
from tests import domainfactory, modelfactory


def list_item_from_invoice(invoice: Invoice, creditor_name: str) -> InvoiceListItem:
    invoice_id = cast(InvoiceId, invoice.id)
    return InvoiceListItem(
        id=invoice_id,
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor,
        creditor_name=creditor_name,
        status=invoice.status,
        currency=invoice.currency(),
        external_invoice_id=invoice.external_invoice_id,
        net=invoice.net(),
        tax=invoice.tax(),
        total=invoice.total(),
        comment=invoice.comment,
        conversions=invoice.conversions(),
        url=reverse("invoices:detail", kwargs={"pk": invoice_id}),
        has_invalid_contract_years=False,
    )


def invoice_matching_number(query_str: str) -> tuple[Invoice, Creditor]:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.number = query_str
    invoice.id = invoice_service.save(invoice)
    return invoice, creditor


def invoice_matching_creditor(query_str: str) -> tuple[Invoice, Creditor]:
    creditor = modelfactory.creditor(name=query_str)
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.id = invoice_service.save(invoice)
    return invoice, creditor


def create_non_matching_invoice() -> None:
    no_match_creditor = modelfactory.creditor(name="NO_MATCH")
    non_matching = domainfactory.invoice(creditor=CreditorId(no_match_creditor.pk), positions=())
    non_matching.number = "NO_MATCH"
    non_matching.id = invoice_service.save(non_matching)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "create_matching_invoice_and_creditor",
    [invoice_matching_number, invoice_matching_creditor],
)
def test__searching_by_generic_criterion_finds_matching_invoices(
    create_matching_invoice_and_creditor: Callable[[str], tuple[Invoice, Creditor]],
) -> None:
    query_str = "the-keyword"
    invoice, creditor = create_matching_invoice_and_creditor(query_str)
    create_non_matching_invoice()

    actual = invoice_repository.search(invoice_repository.GenericSearchCriterion(query_str))

    assert actual == [list_item_from_invoice(invoice, creditor.name)]

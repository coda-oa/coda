import pytest
from django.contrib import messages
from django.test import Client
from django.urls import reverse

from coda.contexts.finance.services.invoice_import import save
from coda.domain.finance.invoice import CreditorId
from coda.domain.money._currency import Currency
from tests import domainfactory, modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_unassigned_costs__cannot_be_paid(client: Client) -> None:
    invoice = domainfactory.invoice(positions=[], creditor=CreditorId(modelfactory.creditor().pk))
    invoice.reset_payment()

    position = domainfactory.free_position(Currency.EUR)
    position.assign_funding(None, position.cost.amount / 2)
    invoice.positions = [position]

    invoice.id = save(invoice)

    response = client.post(
        reverse("invoices:pay_invoice", kwargs={"pk": invoice.id}),
        data={"action": "pay"},
        follow=True,
    )

    msg = list(messages.get_messages(response.wsgi_request))
    error_msg = msg.pop()
    assert error_msg.message == "Invoice has unassigned costs"

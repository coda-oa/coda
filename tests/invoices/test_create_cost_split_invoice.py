import pytest
from django.test import Client
from django.urls import reverse
from faker import Faker

from coda.apps.invoices import repository
from coda.domain.invoice import PaymentStatus
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from tests import modelfactory
from tests.invoices.test_create_invoice_view import create_free_position_input

_faker = Faker()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_invoice_with_split_position_and_unassigned_costs__invoice_is_saved_with_unassigned_costs(
    client: Client,
) -> None:
    creditor = modelfactory.creditor()
    status = PaymentStatus.Unpaid
    head_data = {
        "action": "create",
        "number": _faker.pystr(),
        "date": _faker.date(),
        "creditor": str(creditor.pk),
        "status": status.value,
        "currency": Currency.EUR.code,
        "number-of-positions": "1",
    }

    position_data = create_free_position_input()
    position_data["position-1-use-split"] = "true"
    position_data["position-1-own-split-cost-amount"] = "100"
    post_data = head_data | position_data

    client.post(reverse("invoices:create"), post_data)

    invoice = repository.first()
    assert invoice is not None

    split_position, *_ = invoice.positions
    assert split_position.unassigned_costs() == Money(100, Currency.EUR)

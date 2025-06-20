from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.invoices import repository
from coda.domain.invoice import CreditorId
from coda.domain.money._currency import Currency
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_conversion_view__save__adds_conversion_to_invoice(client: Client) -> None:
    creditor = CreditorId(modelfactory.creditor().id)
    expected = domainfactory.invoice(creditor=creditor, positions=())
    expected.id = repository.create(expected)

    expected.add_conversion(Decimal("2.0"), Currency.JPY)

    data = {"currency": Currency.JPY.code, "exchange_rate": "2"}
    url = reverse("invoices:add_conversion", kwargs={"pk": expected.id})
    _ = client.post(url, data)

    actual = repository.get_by_id(expected.id)
    assert_invoice_eq(expected, actual)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_conversion_view__save__updates_conversion_in_invoice(client: Client) -> None:
    creditor = CreditorId(modelfactory.creditor().id)
    expected = domainfactory.invoice(creditor=creditor, positions=())
    expected.add_conversion(Decimal("2.0"), Currency.JPY)
    expected.id = repository.create(expected)

    data = {"currency": Currency.JPY.code, "exchange_rate": "4", "row": "0"}
    url = reverse("invoices:update_conversion", kwargs={"pk": expected.id})
    _ = client.post(url, data)

    expected.add_conversion(Decimal("4.0"), Currency.JPY)

    actual = repository.get_by_id(expected.id)
    assert_invoice_eq(expected, actual)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__delete_conversion_view__delete__removes_conversion_from_invoice(client: Client) -> None:
    creditor = CreditorId(modelfactory.creditor().id)
    expected = domainfactory.invoice(creditor=creditor, positions=())
    expected.add_conversion(Decimal("2.0"), Currency.JPY)
    expected.id = repository.create(expected)

    url = reverse("invoices:delete_conversion", kwargs={"pk": expected.id})
    data = {"currency": Currency.JPY.code}
    _ = client.post(url, data)

    expected.remove_conversion(Currency.JPY)
    actual = repository.get_by_id(expected.id)
    assert_invoice_eq(expected, actual)

from decimal import Decimal
from typing import cast

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.invoices import repository
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.invoice import CreditorId, Invoice, InvoiceId
from coda.domain.money._currency import Currency
from tests import domainfactory, modelfactory
from tests.invoices.test_create_invoice_view import invoice_post_data
from tests.invoices.test_invoice_detail_view import funding_request, invoice_with_position


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__load_conversion_section__foreign_currency_is_selected__conversion_section_is_rendered(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    url = reverse("invoices:conversions_section")
    selected_currency = Currency.JPY.code
    data = {"currency": selected_currency}

    response = client.get(url, data)
    html_response = response.content.decode()

    assert response.status_code == 200
    assert 'id="exchange_rate"' in html_response
    assert 'value="EUR"' in html_response


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__remove_conversion_section__home_currency_is_selected__conversion_section_is_not_rendered(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    url = reverse("invoices:conversions_section")
    data = {"currency": Currency.EUR.code}

    response = client.get(url, data)
    html_response = response.content.decode()

    assert response.status_code == 200
    assert html_response.strip() == ""


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_foreign_currency_and_conversion__is_saved__invoice_has_conversion(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    url = reverse("invoices:create")
    post_data = invoice_post_data(positions=[])
    post_data["currency"] = Currency.JPY.code
    post_data["conversion_currency_EUR"] = Currency.EUR.code
    post_data["exchange_rate_EUR"] = "1.5"

    response = client.post(url, post_data)

    assert response.status_code == 302
    invoice = repository.first()
    assert invoice is not None
    conversions = invoice.conversions()

    assert Currency.EUR in conversions
    assert conversions[Currency.EUR] == Decimal("1.5")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__saved_invoice_with_conversion__form_field_for_exchange_rate_is_cleared_and_invoice_is_saved__ivoice_has_no_conversion(
    client: Client,
) -> None:
    creditor = CreditorId(modelfactory.creditor().id)
    invoice = domainfactory.invoice(creditor=creditor, positions=())
    invoice.add_conversion(Decimal("2.0"), Currency.JPY)
    invoice.id = repository.create(invoice)
    data = {
        **invoice_form_data(invoice),
        "conversion_currency_JPY": Currency.JPY.code,
        "exchange_rate_JPY": "",
    }
    url = reverse("invoices:update", kwargs={"pk": invoice.id})

    _ = client.post(url, data)

    updated_invoice = repository.get_by_id(invoice.id)
    assert updated_invoice.conversions() == {}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__saved_invoice_with_conversion__invoice_currency_is_changed_to_home_currency__conversion_is_deleted(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.USD)
    invoice = build_invoice_with_JPY_currency_and_USD_conversion()
    data = {**invoice_form_data(invoice), "currency": Currency.USD.code}
    url = reverse("invoices:update", kwargs={"pk": invoice.id})

    _ = client.post(url, data)

    updated_invoice = repository.get_by_id(cast(InvoiceId, invoice.id))
    assert Currency.USD not in updated_invoice.conversions()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_foreign_curency_has_conversion_to_home_currency__home_currency_is_changed__conversion_to_old_home_currency_remains(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    invoice = build_invoice_with_JPY_currency_and_USD_conversion()
    invoice.add_conversion(Decimal("2.0"), Currency.EUR)
    repository.update(invoice)
    data = invoice_form_data(invoice) | {"currency": Currency.EUR.code}
    url = reverse("invoices:detail", kwargs={"pk": invoice.id})

    GlobalPreferences.set_home_currency(Currency.USD)
    _ = client.post(url, data)

    updated_invoice = repository.get_by_id(cast(InvoiceId, invoice.id))
    assert updated_invoice.conversions() == invoice.conversions()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_foreign_curency_has_conversion_to_home_currency__home_currency_is_changed__the_conversion_to_the_old_home_currency_is_still_displayed(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    invoice = build_invoice_with_JPY_currency_and_USD_conversion()
    invoice.add_conversion(Decimal("2.0"), Currency.EUR)
    repository.update(invoice)
    data = {**invoice_form_data(invoice), "currency": Currency.JPY.code}
    url = reverse("invoices:update", kwargs={"pk": invoice.id})

    GlobalPreferences.set_home_currency(Currency.USD)
    response = client.get(url, data)

    assert "conversions" in response.context
    assert Currency.EUR in response.context["conversions"]
    assert response.context["conversions"][Currency.EUR] == Decimal("2.0")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_foreign_currency_and_multiple_conversions__home_currency_is_changed__correct_exchange_rate_for_current_home_currency_is_returned(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    invoice = build_invoice_with_JPY_currency_and_USD_conversion()
    invoice.add_conversion(Decimal("2.0"), Currency.EUR)
    repository.update(invoice)
    data = {**invoice_form_data(invoice), "currency": Currency.JPY.code}
    url = reverse("invoices:update", kwargs={"pk": invoice.id})

    GlobalPreferences.set_home_currency(Currency.USD)
    response = client.get(url, data)

    assert response.context["home_currency"] == Currency.USD.code
    assert response.context["exchange_rate"] == Decimal("3.0")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_foreign_currency_and_multiple_conversions__home_currency_is_changed__conversion_to_old_home_currency_can_be_deleted(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    invoice = build_invoice_with_JPY_currency_and_USD_conversion()
    invoice.add_conversion(Decimal("2.0"), Currency.EUR)
    repository.update(invoice)
    GlobalPreferences.set_home_currency(Currency.USD)
    data = {
        **invoice_form_data(invoice),
        "currency": Currency.JPY.code,
        "conversion_currency_USD": Currency.USD.code,
        "exchange_rate_USD": "3.0",
    }
    url = reverse("invoices:update", kwargs={"pk": invoice.id})

    _ = client.post(url, data)

    updated_invoice = repository.get_by_id(cast(InvoiceId, invoice.id))
    assert Currency.USD in updated_invoice.conversions()
    assert Currency.EUR not in updated_invoice.conversions()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_foreign_currency_and_exchange_rate_to_home_currency_is_zero__invoice_is_saved__conversion_with_exchange_rate_zero_is_not_saved(
    client: Client,
) -> None:
    GlobalPreferences.set_home_currency(Currency.EUR)
    invoice = build_invoice_with_JPY_currency_and_USD_conversion()
    data = {
        **invoice_form_data(invoice),
        "currency": Currency.JPY.code,
        "conversion_currency_EUR": Currency.EUR.code,
        "exchange_rate_EUR": "0",
    }
    url = reverse("invoices:update", kwargs={"pk": invoice.id})

    _ = client.post(url, data)

    updated_invoice = repository.get_by_id(cast(InvoiceId, invoice.id))
    assert Currency.EUR not in updated_invoice.conversions()


def invoice_form_data(invoice: Invoice) -> dict[str, str]:
    return {
        "number": invoice.number,
        "currency": "EUR",
        "creditor": str(invoice.creditor),
        "date": invoice.date.isoformat(),
        "status": invoice.status.value,
    }


def build_invoice_with_JPY_currency_and_USD_conversion() -> Invoice:
    fr = funding_request()
    publication_position = domainfactory.publication_position(
        fr.publication.id, currency=Currency.JPY
    )
    invoice = invoice_with_position(publication_position)
    invoice.add_conversion(Decimal("3.0"), Currency.USD)
    repository.update(invoice)
    return invoice

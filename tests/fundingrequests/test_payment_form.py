from decimal import Decimal

from django.test import SimpleTestCase

from coda.apps.fundingrequests.forms import PaymentForm
from coda.domain.money import Currency


def payment_form_data(
    amount: str, currency: Currency, method: str = "unknown"
) -> dict[str, str]:
    return {"amount": amount, "currency": currency.code, "method": method}


class PaymentFormCurrencyScaleTests(SimpleTestCase):
    def test__amount_within_currency_minor_units__is_valid(self) -> None:
        # Regression: a KWD amount carries 3 decimals because Money quantizes
        # to the currency's minor units. The form used to hardcode 2 and
        # rejected every such payment.
        form = PaymentForm(data=payment_form_data("123.450", Currency.KWD))

        self.assertTrue(form.is_valid(), form.errors)

    def test__amount_beyond_currency_minor_units__is_invalid(self) -> None:
        form = PaymentForm(data=payment_form_data("123.4500", Currency.KWD))

        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test__amount_with_decimals_for_zero_minor_unit_currency__is_invalid(self) -> None:
        form = PaymentForm(data=payment_form_data("100.0", Currency.CLP))

        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test__amount_beyond_two_unit_currency_minor_units__is_invalid(self) -> None:
        form = PaymentForm(data=payment_form_data("10.001", Currency.EUR))

        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test__two_decimal_amount_for_two_unit_currency__is_valid(self) -> None:
        form = PaymentForm(data=payment_form_data("67.18", Currency.EUR))

        self.assertTrue(form.is_valid(), form.errors)

    def test__four_decimal_amount_for_four_minor_unit_currency__is_valid(self) -> None:
        form = PaymentForm(data=payment_form_data("44.6300", Currency.UYW))

        self.assertTrue(form.is_valid(), form.errors)

    def test__amount_is_preserved_exactly_on_clean(self) -> None:
        form = PaymentForm(data=payment_form_data("16.710", Currency.IQD))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["amount"], Decimal("16.710"))

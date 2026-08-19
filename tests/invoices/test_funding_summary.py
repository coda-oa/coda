from decimal import Decimal

import pytest

from coda.apps.invoices import funding_summary
from coda.apps.invoices.models import CurrencyConversion
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.invoices.funding_helpers import create_assignment


@pytest.mark.django_db
def test__summary__paid_invoice_counts_as_spent() -> None:
    sut = modelfactory.budget()
    paid_invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("100.00"), "EUR", paid_invoice, status=PaymentStatus.Paid.value)

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(100, Currency.EUR)
    assert summary.reserved == Money(0, Currency.EUR)


@pytest.mark.django_db
def test__summary__unpaid_invoice_counts_as_reserved() -> None:
    sut = modelfactory.budget()
    unpaid_invoice = modelfactory.invoice()
    create_assignment(
        sut, Decimal("50.00"), "EUR", unpaid_invoice, status=PaymentStatus.Unpaid.value
    )

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(0, Currency.EUR)
    assert summary.reserved == Money(50, Currency.EUR)


@pytest.mark.django_db
def test__summary__rejected_invoice_listed_but_not_counted() -> None:
    sut = modelfactory.budget()
    rejected_invoice = modelfactory.invoice()
    create_assignment(
        sut, Decimal("100.00"), "EUR", rejected_invoice, status=PaymentStatus.Rejected.value
    )

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(0, Currency.EUR)
    assert summary.reserved == Money(0, Currency.EUR)
    assert len(summary.invoices) == 1
    assert summary.invoices[0].invoice == rejected_invoice
    assert summary.invoices[0].converted_amount == Money(100, Currency.EUR)


@pytest.mark.django_db
def test__summary__ignores_assignments_of_other_funding_sources() -> None:
    sut = modelfactory.budget()
    other = modelfactory.budget()
    invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("60.00"), "EUR", invoice)
    create_assignment(other, Decimal("40.00"), "EUR", invoice)

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(0, Currency.EUR)
    assert summary.reserved == Money(60, Currency.EUR)


@pytest.mark.django_db
def test__summary__without_assignments_is_empty() -> None:
    sut = modelfactory.budget()

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(0, Currency.EUR)
    assert summary.reserved == Money(0, Currency.EUR)
    assert summary.invoices == ()
    assert summary.unconverted == ()


@pytest.mark.django_db
def test__summary__sums_assignments_per_invoice() -> None:
    sut = modelfactory.budget()
    invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("30"), "EUR", invoice)
    create_assignment(sut, Decimal("40"), "EUR", invoice)

    summary = funding_summary.funding_source_summary(sut)

    assert len(summary.invoices) == 1
    assert summary.invoices[0].invoice == invoice
    assert summary.invoices[0].converted_amount == Money(70, Currency.EUR)


@pytest.mark.django_db
def test__summary__converts_amounts_to_home_currency() -> None:
    sut = modelfactory.budget()
    invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("100"), "USD", invoice)
    CurrencyConversion.objects.create(
        invoice=invoice, target_currency="EUR", exchange_rate=Decimal("0.85")
    )

    summary = funding_summary.funding_source_summary(sut)

    assert summary.reserved == Money(85, Currency.EUR)
    assert summary.invoices[0].converted_amount == Money(85, Currency.EUR)


@pytest.mark.django_db
def test__summary__missing_conversion_excludes_invoice_from_totals() -> None:
    sut = modelfactory.budget()
    invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("100"), "USD", invoice)

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(0, Currency.EUR)
    assert summary.reserved == Money(0, Currency.EUR)
    assert summary.invoices == ()
    assert len(summary.unconverted) == 1
    assert summary.unconverted[0].invoice == invoice
    assert summary.unconverted[0].unconverted_amounts == (Money(100, Currency.USD),)


@pytest.mark.django_db
def test__summary__uses_configured_home_currency() -> None:
    GlobalPreferences.objects.create(home_currency="USD")
    sut = modelfactory.budget()
    invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("100"), "EUR", invoice)
    CurrencyConversion.objects.create(
        invoice=invoice, target_currency="USD", exchange_rate=Decimal("1.2")
    )

    summary = funding_summary.funding_source_summary(sut)

    assert summary.reserved == Money(120, Currency.USD)


@pytest.mark.django_db
def test__summary__spans_multiple_currencies__sums_into_home_currency() -> None:
    sut = modelfactory.budget()
    paid_eur_invoice = modelfactory.invoice()
    paid_usd_invoice = modelfactory.invoice()
    create_assignment(sut, Decimal("100"), "EUR", paid_eur_invoice, status=PaymentStatus.Paid.value)
    create_assignment(sut, Decimal("100"), "USD", paid_usd_invoice, status=PaymentStatus.Paid.value)
    CurrencyConversion.objects.create(
        invoice=paid_usd_invoice, target_currency="EUR", exchange_rate=Decimal("0.85")
    )

    summary = funding_summary.funding_source_summary(sut)

    assert summary.spent == Money(185, Currency.EUR)

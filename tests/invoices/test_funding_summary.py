from decimal import Decimal

import pytest

from coda.apps.invoices import funding_summary
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

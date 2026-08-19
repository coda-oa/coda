"""Aggregation of funding source usage for the detail page."""

from dataclasses import dataclass

from django.db.models import QuerySet

from coda.apps.invoices.models import FundingAssignment, FundingSource, Invoice
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.money import Currency, Money


@dataclass(frozen=True)
class InvoiceUsage:
    invoice: Invoice
    converted_amount: Money


@dataclass(frozen=True)
class FundingSourceSummary:
    spent: Money
    reserved: Money
    invoices: tuple[InvoiceUsage, ...]
    unconverted: tuple[InvoiceUsage, ...]


def funding_source_summary(
    funding_source: FundingSource,
    home_currency: Currency | None = None,
) -> FundingSourceSummary:
    home = home_currency or GlobalPreferences.get_home_currency()

    spent = Money(0, home)
    reserved = Money(0, home)
    usages: list[InvoiceUsage] = []

    for assignment in _assignments_for(funding_source):
        position = assignment.position
        invoice = position.invoice
        amount = Money(assignment.amount, Currency.from_code(position.cost_currency))
        usages.append(InvoiceUsage(invoice=invoice, converted_amount=amount))

        if invoice.status == PaymentStatus.Paid.value:
            spent += amount
        elif invoice.status == PaymentStatus.Unpaid.value:
            reserved += amount

    return FundingSourceSummary(
        spent=spent,
        reserved=reserved,
        invoices=tuple(usages),
        unconverted=(),
    )


def _assignments_for(funding_source: FundingSource) -> QuerySet[FundingAssignment]:
    return FundingAssignment.objects.filter(funding_source=funding_source)

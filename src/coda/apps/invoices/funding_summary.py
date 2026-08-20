"""Aggregation of funding source usage for the detail page."""

from dataclasses import dataclass, field
from decimal import Decimal
from collections.abc import Iterable

from django.db.models import QuerySet

from coda.apps.invoices.models import FundingAssignment, FundingSource, Invoice
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.money import Currency, Money


@dataclass(frozen=True)
class InvoiceUsage:
    invoice: Invoice
    converted_amount: Money
    unconverted_amounts: tuple[Money, ...] = ()


@dataclass(frozen=True)
class FundingSourceSummary:
    spent: Money
    reserved: Money
    invoices: tuple[InvoiceUsage, ...]
    unconverted: tuple[InvoiceUsage, ...]


@dataclass
class _Bucket:
    invoice: Invoice
    converted_total: Money | None = None
    unconverted_amounts: list[Money] = field(default_factory=list)


def funding_source_summary(
    funding_source: FundingSource,
    home_currency: Currency | None = None,
) -> FundingSourceSummary:
    home = home_currency or GlobalPreferences.get_home_currency()

    spent = Money(0, home)
    reserved = Money(0, home)
    buckets: dict[int, _Bucket] = {}
    conversion_cache: dict[int, dict[str, Decimal]] = {}

    for assignment in _assignments_for(funding_source):
        position = assignment.position
        invoice = position.invoice
        bucket = buckets.setdefault(invoice.pk, _Bucket(invoice=invoice))

        amount = Money(assignment.amount, Currency.from_code(position.cost_currency))
        if amount.currency != home:
            rate = _conversion_rate(conversion_cache, invoice, home)
            if rate is None:
                bucket.unconverted_amounts.append(amount)
                continue
            amount = amount.convert_to(home, lambda _origin, _target, rate=rate: rate)

        if bucket.converted_total is None:
            bucket.converted_total = amount
        else:
            bucket.converted_total = bucket.converted_total + amount

        if invoice.status == PaymentStatus.Paid.value:
            spent += amount
        elif invoice.status == PaymentStatus.Unpaid.value:
            reserved += amount

    return FundingSourceSummary(
        spent=spent,
        reserved=reserved,
        invoices=_sorted(
            InvoiceUsage(
                invoice=bucket.invoice,
                converted_amount=bucket.converted_total or Money(0, home),
            )
            for bucket in buckets.values()
            if not bucket.unconverted_amounts and bucket.converted_total is not None
        ),
        unconverted=_sorted(
            InvoiceUsage(
                invoice=bucket.invoice,
                converted_amount=bucket.converted_total or Money(0, home),
                unconverted_amounts=tuple(bucket.unconverted_amounts),
            )
            for bucket in buckets.values()
            if bucket.unconverted_amounts
        ),
    )


def _sorted(usages: Iterable[InvoiceUsage]) -> tuple[InvoiceUsage, ...]:
    return tuple(
        sorted(usages, key=lambda usage: (usage.invoice.date, usage.invoice.number), reverse=True)
    )


def _assignments_for(funding_source: FundingSource) -> QuerySet[FundingAssignment]:
    return (
        FundingAssignment.objects.filter(funding_source=funding_source)
        .select_related("position", "position__invoice")
        .prefetch_related("position__invoice__currency_conversions")
    )


def _conversion_rate(
    cache: dict[int, dict[str, Decimal]], invoice: Invoice, home: Currency
) -> Decimal | None:
    if invoice.pk not in cache:
        cache[invoice.pk] = {
            conversion.target_currency: conversion.exchange_rate
            for conversion in invoice.currency_conversions.all()
        }
    return cache[invoice.pk].get(home.code)

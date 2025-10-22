import logging
from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal
from typing import TypeVar

from django.db import transaction
from django.db.models import F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices import mapper as invoice_mapper
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.domain.date import DateRange
from coda.domain.finance.invoice import (
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    PaymentStatus,
)
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Currency
from coda.domain.publication import PublicationId


def first() -> Invoice | None:
    model = InvoiceModel.objects.first()
    if not model:
        return None

    return invoice_mapper.as_domain_object(model)


def get_by_id(invoice_id: InvoiceId) -> Invoice:
    return invoice_mapper.as_domain_object(InvoiceModel.objects.get(id=invoice_id))


def get_by_creditor(creditor_id: CreditorId) -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered_date_desc(InvoiceModel.objects.filter(creditor_id=creditor_id)),
        invoice_mapper.as_domain_object,
    )


def all() -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered_date_desc(InvoiceModel.objects.all()), invoice_mapper.as_domain_object
    )


def invoice_with_publication(publication_id: PublicationId) -> Invoice | None:
    invoice = InvoiceModel.objects.filter(positions__publication_id=publication_id).first()

    if not invoice:
        return None

    return invoice_mapper.as_domain_object(invoice)


def get_other_paid_invoice_with_publication(
    original_invoice: Invoice, publication_id: PublicationId
) -> Invoice | None:
    if not original_invoice.id:
        raise UnsavedInvoice(original_invoice)

    invoice = (
        InvoiceModel.objects.filter(
            positions__publication_id=publication_id,
            status=PaymentStatus.Paid.value,
        )
        .exclude(id=original_invoice.id)
        .first()
    )

    if not invoice:
        return None

    return invoice_mapper.as_domain_object(invoice)


def search(
    *,
    generic_search: str | None = None,
    status: PaymentStatus | None = None,
    date_range: DateRange | None = None,
    funding_source: FundingSourceId | None = None,
    has_external_id: bool | None = None,
    home_currency: Currency | None = None,
    has_foreign_currency: bool | None = None,
    sort_by: str = "date_desc",
    contract_id: str | int | None = None,
    contract_year: str | int | None = None,
) -> Sequence[InvoiceListItem]:
    query = (
        generic_search_criterion(generic_search)
        & status_criterion(status)
        & date_range_criterion(date_range)
        & funding_source_criterion(funding_source)
        & external_id_criterion(has_external_id)
        & contract_criterion(contract_id)
        & contract_year_criterion(contract_year)
    )

    logging.info("Query: %s", query)
    qs = InvoiceModel.objects.filter(query).distinct()

    # Apply foreign currency filter at the database level for better performance
    if has_foreign_currency and home_currency:
        qs = foreign_currency_without_conversion_queryset(qs, home_currency)

    list_items = get_sorted_list_items(qs, sort_by)

    return list_items


T = TypeVar("T")


def empty_if_none(crit: Callable[[T], Q]) -> Callable[[T | None], Q]:
    def _wrapped(value: T | None) -> Q:
        if value is None:
            return Q()
        return crit(value)

    return _wrapped


@empty_if_none
def generic_search_criterion(generic_search: str) -> Q:
    return (
        invoice_number_criterion(generic_search)
        | creditor_criterion(generic_search)
        | Q(positions__publication__fundingrequest__request_id__iexact=generic_search)
        | Q(external_invoice_id__iexact=generic_search)
    )


@empty_if_none
def invoice_number_criterion(invoice_number: str) -> Q:
    return Q(number__icontains=invoice_number)


@empty_if_none
def creditor_criterion(creditor: str) -> Q:
    return Q(creditor__name__icontains=creditor)


@empty_if_none
def status_criterion(status: PaymentStatus) -> Q:
    return Q(status=status.value)


@empty_if_none
def date_range_criterion(date_range: DateRange) -> Q:
    return Q(date__range=(date_range.start, date_range.end))


@empty_if_none
def funding_source_criterion(funding_source: FundingSourceId) -> Q:
    return Q(positions__funding_source__exact=funding_source)


@empty_if_none
def external_id_criterion(has_external_id: bool) -> Q:
    return (
        Q(external_invoice_id__isnull=True)
        | Q(external_invoice_id__exact="")
        | Q(positions__external_position_id__isnull=True)
        | Q(positions__external_position_id__exact="")
    )


def foreign_currency_without_conversion_queryset(
    qs: QuerySet[InvoiceModel], home_currency: Currency
) -> QuerySet[InvoiceModel]:
    """
    Filter invoices at the database level to only include those with foreign currency and no conversions.
    This is much more efficient than filtering in Python after fetching all data.
    """
    return qs.filter(
        # Foreign currency: positions have currency different from home currency
        ~Q(positions__cost_currency=home_currency.code),
        # No conversions: no currency conversion records
        currency_conversions__isnull=True,
    ).distinct()


@empty_if_none
def contract_criterion(contract_id: str | int) -> Q:
    return Q(positions__contract_id=contract_id) | Q(
        positions__publication__attached_contracts__contract_id=contract_id
    )


@empty_if_none
def contract_year_criterion(contract_year: str | int) -> Q:
    return Q(positions__contract_year=contract_year) | Q(
        positions__publication__attached_contracts__contract_year=contract_year
    )


def get_sorted_list_items(qs: QuerySet[InvoiceModel], sort_by: str) -> Sequence[InvoiceListItem]:
    sort_functions = {
        "alphabetical": _ordered_alphabetically,
        "date_asc": _ordered_date_asc,
        "date_desc": _ordered_date_desc,
    }
    sort_function = sort_functions.get(sort_by, _ordered_date_desc)
    qs = _annotate_position_based_data(
        sort_function(qs).select_related("creditor").prefetch_related("currency_conversions")
    )

    return [invoice_mapper.as_list_item(model) for model in qs]


def _annotate_position_based_data(qs: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return qs.annotate(
        net_total=Coalesce(Sum("positions__cost_amount"), Decimal("0")),
        tax_total=Coalesce(
            Sum(F("positions__cost_amount") * F("positions__tax_rate")), Decimal("0")
        ),
        first_position_currency=Coalesce(
            "positions__cost_currency",
            Value("EUR"),  # Default currency if no positions
        ),
    )


def create(invoice: Invoice) -> InvoiceId:
    if invoice.id:
        raise InvoiceAlreadyExists(invoice.id)

    invoice_model = invoice_mapper.as_django_model(invoice)
    invoice_model.save()
    invoice_mapper.synchronize_relationships(invoice, invoice_model)

    return InvoiceId(invoice_model.id)


@transaction.atomic
def bulk_create(invoices: Iterable[Invoice]) -> list[InvoiceId]:
    models = InvoiceModel.objects.bulk_create(
        invoice_mapper.as_django_model(invoice) for invoice in invoices
    )

    for invoice, invoice_model in zip(invoices, models):
        invoice_mapper.synchronize_relationships(invoice, invoice_model)

    return [InvoiceId(m.id) for m in models]


def update(invoice: Invoice) -> None:
    if not invoice.id:
        raise UnsavedInvoice(invoice)

    invoice_model = invoice_mapper.as_django_model(invoice)
    invoice_mapper.synchronize_relationships(invoice, invoice_model)
    invoice_model.save()


def delete(invoice_id: InvoiceId) -> None:
    InvoiceModel.objects.filter(id=invoice_id).delete()


class InvoiceAlreadyExists(ValueError):
    def __init__(self, invoice_id: InvoiceId) -> None:
        super().__init__(f"Invoice with ID {invoice_id} already exists.")


class UnsavedInvoice(ValueError):
    def __init__(self, invoice: Invoice) -> None:
        super().__init__(f"Invoice {invoice.number} is not saved yet.")


def _ordered_alphabetically(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("number")


def _ordered_date_asc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("date")


def _ordered_date_desc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("-date")

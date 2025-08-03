import logging
from collections.abc import Callable, Iterable, Sequence
from typing import TypedDict, TypeVar

from django.db import transaction
from django.db.models import Q, QuerySet

from coda.apps.contracts import repository as contract_services
from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices.models import CurrencyConversion
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.domain.contract import ContractYear
from coda.domain.date import DateRange
from coda.domain.invoice import (
    AnyPosition,
    ContractCostType,
    ContractPosition,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    ItemType,
    PaymentStatus,
    Position,
    PublicationCostType,
    TaxRate,
)
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId
from coda.lazyiterable import LazyCachedIterable


def first() -> Invoice | None:
    model = InvoiceModel.objects.first()
    if not model:
        return None

    return as_domain_object(model)


def get_by_id(invoice_id: InvoiceId) -> Invoice:
    return as_domain_object(InvoiceModel.objects.get(id=invoice_id))


def get_by_creditor(creditor_id: CreditorId) -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered_date_desc(InvoiceModel.objects.filter(creditor_id=creditor_id)), as_domain_object
    )


def all() -> Sequence[Invoice]:
    return DomainQuerySet(_ordered_date_desc(InvoiceModel.objects.all()), as_domain_object)


def invoice_with_publication(publication_id: PublicationId) -> Invoice | None:
    invoice = InvoiceModel.objects.filter(positions__publication_id=publication_id).first()

    if not invoice:
        return None

    return as_domain_object(invoice)


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

    return as_domain_object(invoice)


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
    contract_name: Contract | None = None,
    contract_year: int | None = None,
) -> Sequence[Invoice]:
    query = (
        generic_search_criterion(generic_search)
        & status_criterion(status)
        & date_range_criterion(date_range)
        & funding_source_criterion(funding_source)
        & external_id_criterion(has_external_id)
        & contract_criterion(contract_name)
        & contract_year_criterion(contract_year)
    )

    qs = InvoiceModel.objects.filter(query).distinct()

    invoices = get_sorted_invoices(qs, sort_by)

    if has_foreign_currency:
        invoices = foreign_currency_without_conversion(invoices, home_currency)

    return invoices


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


def foreign_currency_without_conversion(
    invoices: Sequence[Invoice], home_currency: Currency | None
) -> Sequence[Invoice]:
    return [
        item for item in invoices if item.currency() != home_currency and not item.conversions()
    ]


@empty_if_none
def contract_criterion(contract_name: Contract) -> Q:
    return Q(positions__contract_id=contract_name)


@empty_if_none
def contract_year_criterion(contract_year: int) -> Q:
    return Q(positions__contract_year=contract_year)


def get_sorted_invoices(qs: QuerySet[InvoiceModel], sort_by: str) -> Sequence[Invoice]:
    sort_functions = {
        "alphabetical": _ordered_alphabetically,
        "date_asc": _ordered_date_asc,
        "date_desc": _ordered_date_desc,
    }
    sort_function = sort_functions.get(sort_by, _ordered_date_desc)
    return list(DomainQuerySet(sort_function(qs), as_domain_object))


def as_domain_object(model: InvoiceModel) -> Invoice:
    invoice = Invoice(
        id=InvoiceId(model.id),
        date=model.date,
        number=model.number,
        creditor=CreditorId(model.creditor_id),
        status=PaymentStatus(model.status),
        positions=LazyCachedIterable(
            _as_position_domain_object(position) for position in model.positions.all()
        ),
        comment=model.comment,
        external_invoice_id=model.external_invoice_id,
    )

    conversions = model.currency_conversions.all()
    for conversion in conversions:
        invoice.add_conversion(
            conversion.exchange_rate, Currency.from_code(conversion.target_currency)
        )

    return invoice


class _CommonPositionArgs(TypedDict):
    cost: Money
    tax_rate: TaxRate
    funding_source: FundingSourceId | None
    external_position_id: str


def _as_position_domain_object(position: PositionModel) -> AnyPosition:
    item = _get_item_from_position_model(position)
    common_args = _extract_common_position_args(position)

    cost_type: PublicationCostType | ContractCostType
    if isinstance(item, ContractYear):
        cost_type = ContractCostType(position.cost_type)
        return ContractPosition(item=item, cost_type=cost_type, **common_args)

    logging.info(
        "Restoring Position %s from DB. Item is %s of type %s. Cost type is %s",
        str(position.id),
        str(item),
        type(item),
        position.cost_type,
    )
    cost_type = PublicationCostType(position.cost_type)
    return Position(item=item, cost_type=cost_type, **common_args)


def _extract_common_position_args(position: PositionModel) -> _CommonPositionArgs:
    return {
        "cost": Money(position.cost_amount, Currency[position.cost_currency]),
        "tax_rate": TaxRate(position.tax_rate),
        "funding_source": (
            FundingSourceId(position.funding_source_id) if position.funding_source_id else None
        ),
        "external_position_id": position.external_position_id,
    }


def _get_item_from_position_model(position: PositionModel) -> ItemType:
    if position.contract and position.contract_year:
        contract = contract_services.as_domain_object(position.contract)
        return contract.in_year(position.contract_year)
    elif position.publication_id:
        return PublicationId(position.publication_id)
    else:
        return position.description


def create(invoice: Invoice) -> InvoiceId:
    if invoice.id:
        raise InvoiceAlreadyExists(invoice.id)

    invoice_model = _create_invoice_model(invoice)
    invoice_model.save()
    _add_positions(invoice, invoice_model)
    _add_conversions(invoice, invoice_model)

    return InvoiceId(invoice_model.id)


def _create_invoice_model(invoice: Invoice) -> InvoiceModel:
    return InvoiceModel(
        number=invoice.number,
        date=invoice.date,
        creditor_id=invoice.creditor,
        comment=invoice.comment,
        status=invoice.status.value,
        external_invoice_id=invoice.external_invoice_id,
    )


@transaction.atomic
def bulk_create(invoices: Iterable[Invoice]) -> list[InvoiceId]:
    models = InvoiceModel.objects.bulk_create(
        _create_invoice_model(invoice) for invoice in invoices
    )

    for invoice, invoice_model in zip(invoices, models):
        _add_positions(invoice, invoice_model)
        _add_conversions(invoice, invoice_model)

    return [InvoiceId(m.id) for m in models]


def _add_conversions(invoice: Invoice, invoice_model: InvoiceModel) -> None:
    CurrencyConversion.objects.bulk_create(
        CurrencyConversion(
            invoice=invoice_model,
            target_currency=target_currency.code,
            exchange_rate=exchange_rate,
        )
        for target_currency, exchange_rate in invoice.conversions().items()
    )


def update(invoice: Invoice) -> None:
    if not invoice.id:
        raise UnsavedInvoice(invoice)

    invoice_model = InvoiceModel.objects.get(id=invoice.id)
    invoice_model.number = invoice.number
    invoice_model.date = invoice.date
    invoice_model.creditor_id = invoice.creditor
    invoice_model.comment = invoice.comment
    invoice_model.status = invoice.status.value
    invoice_model.external_invoice_id = invoice.external_invoice_id
    invoice_model.save()
    invoice_model.positions.all().delete()
    invoice_model.currency_conversions.all().delete()
    _add_positions(invoice, invoice_model)
    _add_conversions(invoice, invoice_model)


def _add_positions(invoice: Invoice, invoice_model: InvoiceModel) -> None:
    PositionModel.objects.bulk_create(
        [_create_position(invoice_model, position) for position in invoice.positions]
    )


def delete(invoice_id: InvoiceId) -> None:
    InvoiceModel.objects.filter(id=invoice_id).delete()


class InvoiceAlreadyExists(ValueError):
    def __init__(self, invoice_id: InvoiceId) -> None:
        super().__init__(f"Invoice with ID {invoice_id} already exists.")


class UnsavedInvoice(ValueError):
    def __init__(self, invoice: Invoice) -> None:
        super().__init__(f"Invoice {invoice.number} is not saved yet.")


def _create_position(m: InvoiceModel, pos: AnyPosition) -> PositionModel:
    match pos.item:
        case ContractYear() as contract_year:
            return PositionModel(
                contract_id=contract_year.contract.id,
                contract_year=contract_year.year,
                cost_amount=pos.cost.amount,
                cost_currency=pos.cost.currency.code,
                cost_type=pos.cost_type.value,
                tax_rate=pos.tax_rate,
                funding_source_id=pos.funding_source,
                invoice_id=m.id,
                external_position_id=pos.external_position_id,
            )
        case PublicationId(pub_id):
            return PositionModel(
                publication_id=pub_id,
                cost_amount=pos.cost.amount,
                cost_currency=pos.cost.currency.code,
                cost_type=pos.cost_type.value,
                tax_rate=pos.tax_rate,
                funding_source_id=pos.funding_source,
                invoice_id=m.id,
                external_position_id=pos.external_position_id,
            )
        case str(description):
            return PositionModel(
                description=description,
                cost_amount=pos.cost.amount,
                cost_currency=pos.cost.currency.code,
                cost_type=pos.cost_type.value,
                tax_rate=pos.tax_rate,
                funding_source_id=pos.funding_source,
                invoice_id=m.id,
                external_position_id=pos.external_position_id,
            )
        case _:
            raise ValueError("Invalid position item")


def _ordered_alphabetically(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("number")


def _ordered_date_asc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("date")


def _ordered_date_desc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("-date")

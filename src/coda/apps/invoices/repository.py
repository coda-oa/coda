from collections.abc import Sequence
import logging
from typing import TypedDict

from django.db.models import Q, QuerySet

from coda.apps.contracts import repository as contract_services
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices.models import CurrencyConversion
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.apps.preferences.models import GlobalPreferences
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
    invoice_number: str | None = None,
    creditor: str | None = None,
    status: PaymentStatus | None = None,
    date_range: DateRange | None = None,
    funding_source: FundingSourceId | None = None,
    has_external_id: bool | None = None,
    pos_has_external_id: bool | None = None,
    has_foreign_currency: bool | None = None,
    invoice_has_conversion: bool | None = None,
    sort_by: str | None = None,
) -> Sequence[Invoice]:
    query = Q()
    if invoice_number:
        query &= Q(number__icontains=invoice_number)

    if creditor:
        query &= Q(creditor__name__icontains=creditor)

    if status:
        query &= Q(status=status.value)

    if date_range:
        query &= Q(date__range=(date_range.start, date_range.end))

    if funding_source:
        query &= Q(positions__funding_source__exact=funding_source)

    if has_external_id is not None:
        empty_q = Q(external_invoice_id__isnull=True) | Q(external_invoice_id__exact="")
        query &= ~empty_q if has_external_id else empty_q

    if pos_has_external_id is not None:
        empty_q = Q(positions__external_position_id__isnull=True) | Q(
            positions__external_position_id__exact=""
        )
        query &= ~empty_q if pos_has_external_id else empty_q

    qs = InvoiceModel.objects.filter(query).distinct()

    if sort_by == "alphabetical":
        qs = _ordered_alphabetically(qs)
    elif sort_by == "date_asc":
        qs = _ordered_date_asc(qs)
    elif sort_by == "date_desc":
        qs = _ordered_date_desc(qs)
    else:
        qs = _ordered_date_desc(qs)

    invoices = list(DomainQuerySet(qs, as_domain_object))

    home_currency = GlobalPreferences.get_home_currency()
    if has_foreign_currency in (True, False):
        invoices = [
            item for item in invoices if (item.currency() != home_currency) == has_foreign_currency
        ]

    if invoice_has_conversion in (True, False):
        invoices = [item for item in invoices if bool(item.conversions()) == invoice_has_conversion]

    return invoices


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

    invoice_model = InvoiceModel.objects.create(
        number=invoice.number,
        date=invoice.date,
        creditor_id=invoice.creditor,
        comment=invoice.comment,
        status=invoice.status.value,
        external_invoice_id=invoice.external_invoice_id,
    )
    _add_positions(invoice, invoice_model)
    _add_conversions(invoice, invoice_model)

    return InvoiceId(invoice_model.id)


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

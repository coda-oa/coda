from collections.abc import Sequence

from django.db.models import Q, QuerySet

from coda.apps.contracts import repository as contract_services
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices.models import CurrencyConversion, Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.domain.contract import ContractYear
from coda.domain.date import DateRange
from coda.domain.invoice import (
    PublicationCostType,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    ItemType,
    PaymentStatus,
    Position,
    TaxRate,
)
from coda.lazyiterable import LazyCachedIterable
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId


def first() -> Invoice | None:
    model = InvoiceModel.objects.first()
    if not model:
        return None

    return as_domain_object(model)


def get_by_id(invoice_id: InvoiceId) -> Invoice:
    return as_domain_object(InvoiceModel.objects.get(id=invoice_id))


def get_by_creditor(creditor_id: CreditorId) -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered(InvoiceModel.objects.filter(creditor_id=creditor_id)), as_domain_object
    )


def all() -> Sequence[Invoice]:
    return DomainQuerySet(_ordered(InvoiceModel.objects.all()), as_domain_object)


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

    return DomainQuerySet(_ordered(InvoiceModel.objects.filter(query)), as_domain_object)


def as_domain_object(model: InvoiceModel) -> Invoice:
    invoice = Invoice(
        id=InvoiceId(model.id),
        date=model.date,
        number=model.number,
        creditor=CreditorId(model.creditor_id),
        status=PaymentStatus(model.status),
        positions=LazyCachedIterable(
            Position(
                item=_get_item_from_position_model(position),
                cost=Money(position.cost_amount, Currency[position.cost_currency]),
                cost_type=PublicationCostType(position.cost_type),
                tax_rate=TaxRate(position.tax_rate),
                funding_source=(
                    FundingSourceId(position.funding_source_id)
                    if position.funding_source_id
                    else None
                ),
                external_position_id=position.external_position_id,
            )
            for position in model.positions.all()
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


def _create_position(m: InvoiceModel, pos: Position[ItemType]) -> PositionModel:
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


def _ordered(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("-date")

from collections.abc import Sequence

from django.db.models import Q, QuerySet

from coda.apps.contracts import repository as contract_services
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.contract import ContractYear
from coda.date import DateRange
from coda.invoice import (
    CostType,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    ItemType,
    PaymentStatus,
    Position,
    TaxRate,
)
from coda.money import Currency, Money
from coda.publication import PublicationId


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
    return Invoice(
        id=InvoiceId(model.id),
        date=model.date,
        number=model.number,
        creditor=CreditorId(model.creditor_id),
        status=PaymentStatus(model.status),
        positions=[
            Position(
                item=_get_item_from_position_model(position),
                cost=Money(position.cost_amount, Currency[position.cost_currency]),
                cost_type=CostType(position.cost_type),
                tax_rate=TaxRate(position.tax_rate),
                funding_source=(
                    FundingSourceId(position.funding_source_id)
                    if position.funding_source_id
                    else None
                ),
            )
            for position in model.positions.all()
        ],
        comment=model.comment,
    )


def _get_item_from_position_model(position: PositionModel) -> ItemType:
    if position.contract and position.contract_year:
        contract = contract_services.as_domain_object(position.contract)
        return contract.in_year(position.contract_year)
    elif position.publication_id:
        return PublicationId(position.publication_id)
    else:
        return position.description


def save(invoice: Invoice) -> InvoiceId:
    if not invoice.id:
        m = InvoiceModel.objects.create(
            number=invoice.number,
            date=invoice.date,
            creditor_id=invoice.creditor,
            comment=invoice.comment,
            status=invoice.status.value,
        )
    else:
        m = InvoiceModel.objects.get(id=invoice.id)
        m.number = invoice.number
        m.date = invoice.date
        m.creditor_id = invoice.creditor
        m.comment = invoice.comment
        m.status = invoice.status.value
        m.positions.all().delete()
        m.save()

    PositionModel.objects.bulk_create(
        [_create_position(m, position) for position in invoice.positions]
    )

    return InvoiceId(m.id)


def delete(invoice_id: InvoiceId) -> None:
    InvoiceModel.objects.filter(id=invoice_id).delete()


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
            )
        case _:
            raise ValueError("Invalid position item")


def _ordered(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("-date")

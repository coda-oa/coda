from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
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


def get_by_id(invoice_id: InvoiceId) -> Invoice:
    return as_domain_object(InvoiceModel.objects.get(id=invoice_id))


def as_domain_object(model: InvoiceModel) -> Invoice:
    return Invoice(
        id=InvoiceId(model.id),
        date=model.date,
        number=model.number,
        creditor=CreditorId(model.creditor_id),
        status=PaymentStatus(model.status),
        positions=[
            Position(
                item=(
                    PublicationId(position.publication_id)
                    if position.publication_id
                    else position.description
                ),
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


def invoice_create(invoice: Invoice) -> InvoiceId:
    m = InvoiceModel.objects.create(
        number=invoice.number,
        date=invoice.date,
        creditor_id=invoice.creditor,
        comment=invoice.comment,
        status=invoice.status.value,
    )

    def _create_position(pos: Position[ItemType]) -> PositionModel:
        match pos.item:
            case int(pub_id):
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

    PositionModel.objects.bulk_create(
        [_create_position(position) for position in invoice.positions]
    )

    return InvoiceId(m.id)

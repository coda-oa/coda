from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.invoice import (
    CostType,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
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
        positions=[
            Position(
                publication=PublicationId(position.publication_id),
                cost=Money(position.cost_amount, Currency[position.cost_currency]),
                cost_type=CostType(position.cost_type),
                tax_rate=TaxRate(position.tax_rate),
                description=position.description,
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
    )

    PositionModel.objects.bulk_create(
        [
            PositionModel(
                publication_id=position.publication,
                cost_amount=position.cost.amount,
                cost_currency=position.cost.currency.code,
                cost_type=position.cost_type.value,
                tax_rate=position.tax_rate,
                description=position.description,
                funding_source_id=position.funding_source,
                invoice_id=m.id,
            )
            for position in invoice.positions
        ]
    )

    return InvoiceId(m.id)

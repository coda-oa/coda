from decimal import Decimal

from django.db.models import QuerySet
from django.urls import reverse

from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.domain.finance.invoice import CreditorId, InvoiceId, PaymentStatus
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Currency, Money


class InvoiceListMapper:
    @staticmethod
    def prefetch(qs: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
        return qs.select_related("creditor").prefetch_related("currency_conversions")

    @staticmethod
    def map(
        model: InvoiceModel,
        net_total: Decimal,
        tax_total: Decimal,
        first_position_currency: str,
        has_invalid_contract_years: bool,
    ) -> InvoiceListItem:
        currency = Currency.from_code(first_position_currency)

        return InvoiceListItem(
            id=InvoiceId(model.pk),
            number=model.number,
            date=model.date,
            creditor=CreditorId(model.creditor.pk),
            creditor_name=model.creditor.name,
            status=PaymentStatus(model.status),
            currency=currency,
            net=Money(net_total, currency),
            tax=Money(tax_total, currency),
            total=Money(net_total + tax_total, currency),
            comment=model.comment,
            external_invoice_id=model.external_invoice_id,
            conversions={
                Currency.from_code(c.target_currency): c.exchange_rate
                for c in model.currency_conversions.all()
            },
            url=reverse("invoices:detail", kwargs={"pk": model.pk}),
            has_invalid_contract_years=has_invalid_contract_years,
        )

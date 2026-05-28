from dataclasses import dataclass
from datetime import date

from django.db.models import Q

from coda.domain.finance.invoice import FundingSourceId


@dataclass
class InvoiceDateRangeCriteria:
    invoice_start: date
    invoice_end: date

    def _to_query(self) -> Q:
        return Q(
            publication__position__invoice__date__gte=self.invoice_start,
            publication__position__invoice__date__lte=self.invoice_end,
        )


@dataclass
class InvoicePaymentStatusCriteria:
    payment_status: str

    def _to_query(self) -> Q:
        return Q(publication__position__invoice__status=self.payment_status)


@dataclass
class InvoiceCreditorCriteria:
    creditor_name: str

    def _to_query(self) -> Q:
        return Q(publication__position__invoice__creditor__name__icontains=self.creditor_name)


@dataclass
class InvoiceFundingSourceCriteria:
    funding_source: FundingSourceId

    def _to_query(self) -> Q:
        return Q(publication__position__funding_assignments__funding_source=self.funding_source)

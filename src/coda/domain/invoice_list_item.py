import datetime
from dataclasses import dataclass
from decimal import Decimal

from coda.domain.invoice import CreditorId, InvoiceId, PaymentStatus
from coda.domain.money import Currency, Money


@dataclass(slots=True, frozen=True)
class InvoiceListItem:
    """
    Read model for invoice list views.
    Contains only the essential fields needed for display in lists,
    without the heavy positions data.
    """

    id: InvoiceId
    number: str
    date: datetime.date
    creditor: CreditorId
    creditor_name: str
    status: PaymentStatus
    currency: Currency
    net: Money
    tax: Money
    total: Money
    comment: str
    external_invoice_id: str
    conversions: dict[Currency, Decimal]
    url: str

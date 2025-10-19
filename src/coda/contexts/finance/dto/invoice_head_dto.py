import datetime
from coda.apps.dto import CodaBaseDto
from coda.domain.invoice import CreditorId, PaymentStatus
from coda.domain.money._currency import Currency


class InvoiceHeadDto(CodaBaseDto):
    number: str
    date: datetime.date
    status: PaymentStatus
    creditor: CreditorId
    external_invoice_id: str = ""
    comment: str = ""
    currency: Currency

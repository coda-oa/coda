import datetime
from typing import Annotated

import pydantic
from coda.apps.dto import CodaBaseDto
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.money._currency import Currency


class InvoiceHeadDto(CodaBaseDto):
    number: str
    date: datetime.date
    status: PaymentStatus
    creditor: int
    external_invoice_id: str = ""
    comment: str = ""
    currency: Annotated[Currency, pydantic.PlainSerializer(lambda c: c.code)]

import datetime
from decimal import Decimal

from pydantic import BaseModel

from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.invoice import CostType, PaymentStatus
from coda.domain.money import Currency

DEFAULT_TAX_RATE = Decimal("19.00")


class CommonPositionImportDto(BaseModel):
    amount: Decimal
    tax_rate: Decimal = DEFAULT_TAX_RATE
    cost_type: CostType
    funding_source: str = ""
    external_id: str = ""


class PublicationPositionDto(CommonPositionImportDto):
    request_id: PublicFundingRequestId
    cost_type: CostType = CostType.Publication_Charge


class ContractPositionImportDto(CommonPositionImportDto):
    contract_name: str
    contract_year: int


class FreePositionImportDto(CommonPositionImportDto):
    description: str = ""
    cost_type: CostType = CostType.Other


class ConversionImportDto(BaseModel):
    target_currency: Currency
    exchange_rate: Decimal


class InvoiceImportDto(BaseModel):
    number: str
    date: datetime.date
    creditor: str
    currency: Currency
    status: PaymentStatus
    external_id: str = ""
    comment: str = ""
    conversion: ConversionImportDto | None = None
    positions: list[CommonPositionImportDto]

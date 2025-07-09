import datetime
from decimal import Decimal

from pydantic import BaseModel, ValidationError, model_validator

from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.invoice import ContractCostType, PaymentStatus, PublicationCostType
from coda.domain.money import Currency

DEFAULT_TAX_RATE = Decimal("19.00")


class CommonPositionImportDto(BaseModel):
    amount: Decimal
    tax_rate: Decimal = DEFAULT_TAX_RATE
    funding_source: str = ""
    external_id: str = ""


class PublicationPositionImportDto(CommonPositionImportDto):
    request_id: PublicFundingRequestId | None = None
    legacy_request_id: str | None = None
    cost_type: PublicationCostType = PublicationCostType.Publication_Charge

    @model_validator(mode="after")
    def validate_request_id(self) -> "PublicationPositionImportDto":
        if not self.request_id and not self.legacy_request_id:
            raise ValidationError("Either request_id or legacy_request_id must be provided.")

        return self


class ContractPositionImportDto(CommonPositionImportDto):
    contract_name: str
    contract_year: int
    cost_type: ContractCostType


class FreePositionImportDto(CommonPositionImportDto):
    description: str = ""
    cost_type: PublicationCostType = PublicationCostType.Other


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

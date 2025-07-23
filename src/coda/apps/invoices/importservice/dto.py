import datetime
from abc import ABC
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainValidator, ValidationError, model_validator

from coda.domain.fundingrequest.identity import InvalidFundingRequestId, PublicFundingRequestId
from coda.domain.invoice import ContractCostType, PaymentStatus, PublicationCostType
from coda.domain.money import Currency

DEFAULT_TAX_RATE = Decimal("19.00")


type PositionType = Literal["publication", "contract", "free"]


class CommonPositionImportDto(BaseModel, ABC):
    type: PositionType
    amount: Decimal
    tax_rate: Decimal = DEFAULT_TAX_RATE
    funding_source: str = ""
    external_id: str = ""


def _validate_request_id(value: str | None) -> str | None:
    if value is None:
        return None

    try:
        id_ = PublicFundingRequestId.from_str(value)
        return str(id_)
    except InvalidFundingRequestId:
        raise ValidationError(f"Invalid request ID: {value}")


type FundingRequestId = Annotated[str | None, PlainValidator(_validate_request_id)]


class PublicationPositionImportDto(CommonPositionImportDto):
    type: Literal["publication"] = "publication"
    request_id: FundingRequestId = None
    legacy_request_id: str | None = None
    cost_type: PublicationCostType = PublicationCostType.Publication_Charge

    @model_validator(mode="after")
    def validate_request_id(self) -> "PublicationPositionImportDto":
        if not self.request_id and not self.legacy_request_id:
            raise ValidationError("Either request_id or legacy_request_id must be provided.")

        return self


class ContractPositionImportDto(CommonPositionImportDto):
    type: Literal["contract"] = "contract"
    contract_name: str
    contract_year: int
    cost_type: ContractCostType


class FreePositionImportDto(CommonPositionImportDto):
    type: Literal["free"] = "free"
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


class InvoiceListImportDto(BaseModel):
    invoices: list[InvoiceImportDto]

import datetime
from abc import ABC
from decimal import Decimal
from typing import Annotated, Literal

from annotated_types import Len
from pydantic import BaseModel, Field, PlainValidator, model_validator

from coda.domain.fundingrequest.identity import InvalidFundingRequestId, PublicFundingRequestId
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.money import Currency

DEFAULT_TAX_RATE = Decimal("19.00")

CurrencyCode = Annotated[str, PlainValidator(lambda v: Currency.from_code(v).code)]
NonEmptyStr = Annotated[str, Len(min_length=1)]

type PositionType = Literal["publication", "contract", "free"]


class FundingAssignmentImportDto(BaseModel):
    type: Literal["budget", "institution"] = "budget"
    name: str
    amount: Decimal | None = None


class CommonPositionImportDto(BaseModel, ABC):
    type: PositionType
    amount: Decimal
    tax_rate: Decimal = DEFAULT_TAX_RATE
    funding_source: str = ""
    external_id: str = ""
    funding_assignments: list[FundingAssignmentImportDto] = Field(default_factory=list)


def _validate_request_id(value: str | None) -> str | None:
    if value is None:
        return None

    try:
        id_ = PublicFundingRequestId.from_str(value)
        return str(id_)
    except InvalidFundingRequestId:
        raise ValueError(f"Invalid request ID: {value}")


type FundingRequestId = Annotated[str | None, PlainValidator(_validate_request_id)]


class PublicationPositionImportDto(CommonPositionImportDto):
    type: PositionType = "publication"
    request_id: FundingRequestId = None
    legacy_request_id: str | None = None
    cost_type: PublicationCostType = PublicationCostType.Publication_Charge

    @model_validator(mode="after")
    def validate_request_id(self) -> "PublicationPositionImportDto":
        if not self.request_id and not self.legacy_request_id:
            raise ValueError("Either request_id or legacy_request_id must be provided.")

        return self


class ContractPositionImportDto(CommonPositionImportDto):
    type: PositionType = "contract"
    contract_name: str
    contract_year: int
    cost_type: ContractCostType


class FreePositionImportDto(CommonPositionImportDto):
    type: PositionType = "free"
    description: str = ""
    cost_type: PublicationCostType = PublicationCostType.Other


class ConversionImportDto(BaseModel):
    target_currency: CurrencyCode
    exchange_rate: Decimal


class InvoiceImportDto(BaseModel):
    number: NonEmptyStr
    date: datetime.date
    creditor: NonEmptyStr
    currency: CurrencyCode
    status: PaymentStatus
    external_id: str = ""
    comment: str = ""
    conversion: ConversionImportDto | None = None
    positions: list[
        PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto
    ]


class InvoiceListImportDto(BaseModel):
    invoices: list[InvoiceImportDto]

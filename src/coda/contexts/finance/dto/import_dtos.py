"""Import DTOs for invoice import workflow.

All Pydantic DTOs used for JSON import validation of invoices.

Field and class descriptions become part of the generated JSON schema
(shown and downloadable on the invoice import page), so keep them
accurate when changing import behavior.
"""

import datetime
from abc import ABC
from decimal import Decimal
from typing import Annotated, Literal

from annotated_types import Len
from pydantic import (
    BaseModel,
    Field,
    PlainValidator,
    ValidationError,
    WithJsonSchema,
    model_validator,
)

from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.fundingrequest.identity import InvalidFundingRequestId, PublicFundingRequestId
from coda.domain.money import Currency

DEFAULT_TAX_RATE = Decimal("19.00")

CurrencyCode = Annotated[
    str, PlainValidator(lambda v: Currency.from_code(v).code), WithJsonSchema({"type": "string"})
]
NonEmptyStr = Annotated[str, Len(min_length=1)]

type PositionType = Literal["publication", "contract", "free"]


class FundingAssignmentImportDto(BaseModel):
    """Assignment of (part of) a position's costs to a funding source."""

    type: Literal["budget", "institution"] = Field(
        default="budget",
        description="Funding source kind: budget or institution.",
    )
    name: str = Field(
        description="Name of the budget or institution. Budgets are created if they don't "
        "exist; institutions must exist before import."
    )
    amount: Decimal | None = Field(
        default=None,
        description="Amount assigned to this funding source. If omitted, the remaining "
        "costs are split equally among the assignments without amount.",
    )


class CommonPositionImportDto(BaseModel, ABC):
    """Fields shared by all invoice position types."""

    amount: Decimal = Field(description="Cost amount; can be negative for credits.")
    tax_rate: Decimal = Field(
        default=DEFAULT_TAX_RATE,
        description="Tax rate as percentage (e.g. 19.00 for 19%).",
    )
    funding_source: str = Field(
        default="",
        description="Single funding source name (backwards compatibility; prefer funding_assignments).",
    )
    external_id: str = Field(default="", description="Position reference ID from external systems.")
    funding_assignments: list[FundingAssignmentImportDto] = Field(
        default_factory=list,
        description="Cost splitting across funding sources; total may not exceed the position cost.",
    )


def _validate_request_id(value: str | None) -> str | None:
    if value is None:
        return None

    try:
        id_ = PublicFundingRequestId.from_str(value)
        return str(id_)
    except InvalidFundingRequestId:
        raise ValueError(f"Invalid request ID: {value}")


type FundingRequestId = Annotated[
    str | None, PlainValidator(_validate_request_id), WithJsonSchema({"type": "string"})
]
type PositionImportDto = (
    "PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto"
)


class PublicationPositionImportDto(CommonPositionImportDto):
    """Invoice position for a publication, linked to a funding request."""

    type: Literal["publication"] = "publication"
    request_id: FundingRequestId = Field(
        default=None,
        description="CODA public funding request ID (format coda-YYYYMMDD-XXXXXXXXXXXX). "
        "Either request_id or legacy_request_id is required.",
    )
    legacy_request_id: str | None = Field(
        default=None,
        description="Funding request ID from the legacy system. Either request_id or "
        "legacy_request_id is required.",
    )
    cost_type: PublicationCostType = Field(
        default=PublicationCostType.Publication_Charge,
        description="openCost cost type, e.g. gold-oa, hybrid-oa, publication charge, "
        "colour charge, page charge, permission, reprint, submission fee, payment fee, "
        "vat, cover charge, or other.",
    )

    @model_validator(mode="after")
    def validate_request_id(self) -> "PublicationPositionImportDto":
        if not self.request_id and not self.legacy_request_id:
            raise ValidationError("Either request_id or legacy_request_id must be provided.")

        return self


class ContractPositionImportDto(CommonPositionImportDto):
    """Invoice position for a publishing contract."""

    type: Literal["contract"] = "contract"
    contract_name: str = Field(
        description="Name of the contract; the contract must already exist with a matching year."
    )
    contract_year: int = Field(description="Contract year; must be a positive integer.")
    cost_type: ContractCostType = Field(
        description="Contract cost type: publish, read, publish and read, service fee, or vat."
    )


class FreePositionImportDto(CommonPositionImportDto):
    """Invoice position not linked to a publication or contract."""

    type: Literal["free"] = "free"
    description: str = Field(default="", description="Descriptive text for the line item.")
    cost_type: PublicationCostType = Field(
        default=PublicationCostType.Other,
        description="openCost cost type (same options as publication positions; default: other).",
    )


class ConversionImportDto(BaseModel):
    """Currency conversion stored with the invoice."""

    target_currency: CurrencyCode = Field(description="Three-letter target currency code.")
    exchange_rate: Decimal = Field(description="Exchange rate applied to the invoice.")


class InvoiceImportDto(BaseModel):
    """A single invoice to import."""

    number: NonEmptyStr = Field(description="Invoice number as assigned by the creditor.")
    date: datetime.date = Field(description="Invoice date (YYYY-MM-DD).")
    creditor: NonEmptyStr = Field(
        description="Creditor name; created if it doesn't exist (matched case-sensitively)."
    )
    currency: CurrencyCode = Field(description="Three-letter currency code (e.g. EUR, USD).")
    status: PaymentStatus = Field(
        description="Payment status: paid, unpaid, or rejected. Paid invoices must have "
        "all position costs assigned to funding sources."
    )
    external_id: str = Field(
        default="", description="External system reference ID for the invoice."
    )
    comment: str = Field(default="", description="Notes about the invoice.")
    conversion: ConversionImportDto | None = Field(
        default=None, description="Optional currency conversion with target currency and rate."
    )
    positions: list[
        Annotated[
            PublicationPositionImportDto | ContractPositionImportDto | FreePositionImportDto,
            Field(discriminator="type"),
        ]
    ] = Field(description="At least one invoice position.")


class InvoiceListImportDto(BaseModel):
    """Root object of the invoice import file."""

    invoices: list[InvoiceImportDto] = Field(description="Invoices to import.")

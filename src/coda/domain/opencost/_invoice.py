from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from coda.domain.opencost._common import NonEmptyString
from coda.domain.opencost._contract import ContractCostType, DateFormat
from coda.domain.opencost._publication import (
    PublicationCostType,
)

Currency = Annotated[str, StringConstraints(pattern=r"[A-Z]{3}")]


class PublicationAmountPaidType(BaseModel):
    currency: Currency
    amount: Decimal
    cost_type: PublicationCostType
    vat: Decimal | None = None


class AmountInvoice(BaseModel):
    currency: Currency
    amount: Decimal


class Dates(BaseModel):
    invoice: DateFormat | None = None
    paid: DateFormat | None = None


class PublicationInvoiceType(BaseModel):
    amount_invoice: AmountInvoice | None = None
    invoice_number: NonEmptyString | None = None
    amounts_paid: list[PublicationAmountPaidType]
    dates: Dates
    creditor: NonEmptyString | None = None


class ContractAmountPaidType(BaseModel):
    currency: Currency
    amount: Decimal
    cost_type: ContractCostType
    vat: Decimal | None = None


class ContractInvoiceType(BaseModel):
    amount_invoice: AmountInvoice | None = None
    invoice_number: NonEmptyString | None = None
    creditor: NonEmptyString | None = None
    dates: Dates
    amounts_paid: list[ContractAmountPaidType]


class ContractInvoicePeriodType(BaseModel):
    from_: DateFormat = Field(..., alias="from")
    to: DateFormat


class ContractInvoiceGroupType(BaseModel):
    group_id: NonEmptyString | None = None
    invoices_period: ContractInvoicePeriodType | None = None
    invoice: list[ContractInvoiceType] | None = None


class ContractCostDataType(BaseModel):
    invoice_group: list[ContractInvoiceGroupType]

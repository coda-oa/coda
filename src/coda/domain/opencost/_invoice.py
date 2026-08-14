from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from ._types import NonEmptyString, Currency, DateFormat, ContractCostType, PublicationCostType


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

    @model_validator(mode="after")
    def _at_least_one_date(self) -> Self:
        if self.invoice is None and self.paid is None:
            raise ValueError("at least one of 'invoice' or 'paid' must be set")
        return self


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
    group_id: NonEmptyString
    invoices_period: ContractInvoicePeriodType
    invoice: list[ContractInvoiceType] | None = None


class ContractCostDataType(BaseModel):
    invoice_group: list[ContractInvoiceGroupType]

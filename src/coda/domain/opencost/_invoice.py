from decimal import Decimal

from pydantic import BaseModel, Field

from ._types import ContractCostType, Currency, DateFormat, NonEmptyString, PublicationCostType
from ._validators import EitherFieldMixin, RequiredList


class PublicationAmountPaidType(BaseModel):
    currency: Currency
    amount: Decimal
    cost_type: PublicationCostType
    vat: Decimal | None = None


class PublicationAmountsPaid(BaseModel):
    amount_paid: RequiredList[PublicationAmountPaidType]


class AmountInvoice(BaseModel):
    currency: Currency
    amount: Decimal


class Dates(EitherFieldMixin):
    either_fields = ("invoice", "paid")

    invoice: DateFormat | None = None
    paid: DateFormat | None = None


class PublicationInvoiceType(BaseModel):
    amount_invoice: AmountInvoice | None = None
    invoice_number: NonEmptyString | None = None
    amounts_paid: PublicationAmountsPaid
    dates: Dates
    creditor: NonEmptyString | None = None


class ContractAmountPaidType(BaseModel):
    currency: Currency
    amount: Decimal
    cost_type: ContractCostType
    vat: Decimal | None = None


class ContractAmountsPaid(BaseModel):
    amount_paid: RequiredList[ContractAmountPaidType]


class ContractInvoiceType(BaseModel):
    amount_invoice: AmountInvoice | None = None
    invoice_number: NonEmptyString | None = None
    creditor: NonEmptyString | None = None
    dates: Dates
    amounts_paid: ContractAmountsPaid


class ContractInvoicePeriodType(BaseModel):
    from_: DateFormat = Field(..., alias="from")
    to: DateFormat


class ContractInvoiceGroupType(BaseModel):
    group_id: NonEmptyString
    invoices_period: ContractInvoicePeriodType
    invoice: list[ContractInvoiceType] | None = None


class ContractCostDataType(BaseModel):
    invoice_group: RequiredList[ContractInvoiceGroupType]

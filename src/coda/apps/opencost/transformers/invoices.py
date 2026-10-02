"""Building openCost invoice elements out of a CODA invoice.

Publication and contract invoice elements share the same position-line calculations. Each line's
net contribution forms ``amount_invoice``, including costs openCost cannot itemize as an
``amount_paid`` entry. A separate VAT line contributes zero to ``amount_invoice`` and carries
its tax as an ``amount_paid`` amount, without a ``vat`` field.

The invoice kinds differ in their OpenCost cost-type vocabularies; common date and exclusion
rules live in ``_dates_if_exportable``.

An invoice's report-scoped positions arrive as ``OpenCostInvoiceLine`` values. Each line keeps
its amount-paid amount distinct from its contribution to the invoice's net amount.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Protocol, Self

from coda.apps.opencost.issues import ReportItem
from coda.coda_itertools import map_or_none
from coda.domain.finance.costtypes import CostType
from coda.domain.finance.invoice_positions import RegularCostCalculation
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Money
from opencost import (
    AmountInvoice,
    ContractAmountPaidType,
    ContractAmountsPaid,
    ContractCostType,
    ContractInvoiceType,
    Dates,
    PublicationAmountPaidType,
    PublicationAmountsPaid,
    PublicationCostType,
    PublicationInvoiceType,
)


@dataclass(frozen=True)
class LiveInvoice:
    """The invoice fields an openCost invoice element needs, read from a CODA invoice.

    A CODA invoice holds them on its own fields and its creditor; wrapping them keeps the
    invoice rules below indifferent to where an invoice came from.
    """

    invoice_number: str
    creditor: str
    invoice_date: date | None


@dataclass(frozen=True)
class UnmappedCostType:
    """A stored cost type that does not belong to this position's domain vocabulary."""

    value: str

    def is_vat(self) -> bool:
        return self.value == "vat"


type OpenCostCostType = CostType | UnmappedCostType


@dataclass(frozen=True)
class OpenCostInvoiceLine:
    """One report-scoped position in OpenCost amount-paid and invoice-net terms."""

    amount_paid: Money
    cost_type: OpenCostCostType
    vat: Money | None

    def __post_init__(self) -> None:
        if self.vat is not None and self.vat.currency != self.amount_paid.currency:
            raise ValueError("VAT and amount-paid values must use the same currency.")

    @property
    def invoice_net_contribution(self) -> Money:
        if self.cost_type.is_vat():
            return Money(0, self.amount_paid.currency)

        return self.amount_paid

    @classmethod
    def from_position(
        cls,
        *,
        cost: Money,
        cost_type: OpenCostCostType,
        tax_rate: TaxRate,
    ) -> Self:
        is_vat = cost_type.is_vat()
        calculation = RegularCostCalculation.from_money(cost, TaxRate(0) if is_vat else tax_rate)

        return cls(
            amount_paid=calculation.cost,
            cost_type=cost_type,
            vat=None if is_vat else calculation.tax(),
        )


def publication_invoice(
    report_item: ReportItem,
    report_invoice: LiveInvoice,
    positions: Iterable[OpenCostInvoiceLine],
) -> PublicationInvoiceType | None:
    """One invoice element, or ``None`` when openCost cannot be given this invoice at all."""
    rows = list(positions)
    amounts = PUBLICATION_COST_TYPES.amounts_for(rows)
    dates = _dates_if_exportable(report_item, report_invoice, amounts)
    if dates is None:
        return None

    return PublicationInvoiceType(
        invoice_number=_text_or_none(report_invoice.invoice_number),
        creditor=_text_or_none(report_invoice.creditor),
        amounts_paid=PublicationAmountsPaid(amount_paid=amounts.items),
        dates=dates,
        amount_invoice=_amount_invoice_from_lines(rows),
    )


def _amount_invoice_from_lines(
    rows: Sequence[OpenCostInvoiceLine],
) -> AmountInvoice | None:
    """Sum report-scoped net amounts and serialize them as one OpenCost invoice amount."""
    if not rows:
        return None

    net_amount = sum(
        (row.invoice_net_contribution for row in rows),
        start=Money(0, rows[0].amount_paid.currency),
    )
    return _amount_invoice(net_amount)


def contract_invoice(
    report_item: ReportItem,
    report_invoice: LiveInvoice,
    positions: Iterable[OpenCostInvoiceLine],
) -> ContractInvoiceType | None:
    """One contract invoice element."""
    rows = list(positions)
    amounts = CONTRACT_COST_TYPES.amounts_for(rows)
    dates = _dates_if_exportable(report_item, report_invoice, amounts)
    if dates is None:
        return None

    return ContractInvoiceType(
        invoice_number=_text_or_none(report_invoice.invoice_number),
        creditor=_text_or_none(report_invoice.creditor),
        amounts_paid=ContractAmountsPaid(amount_paid=amounts.items),
        dates=dates,
        amount_invoice=_amount_invoice_from_lines(rows),
    )


def _amount_invoice(amount: Money) -> AmountInvoice:
    """Serialize a domain money amount at the OpenCost boundary."""
    return AmountInvoice(amount=amount.amount, currency=amount.currency.code)


class PaidFactory[TPaid, TCostEnum: Enum](Protocol):
    """Creates one openCost amount-paid element from an already accepted cost type."""

    def __call__(
        self,
        *,
        amount: Decimal,
        currency: str,
        cost_type: TCostEnum,
        vat: Decimal | None,
    ) -> TPaid: ...


@dataclass(frozen=True)
class AmountsPaid[TPaid]:
    """What became of an invoice's positions: the amounts, and the rows that were not."""

    items: list[TPaid]
    rejected_cost_types: list[str]
    row_count: int


@dataclass(frozen=True)
class InvoiceCostTypes[TPaid, TCostEnum: Enum]:
    """The openCost vocabulary one invoice kind maps CODA positions onto."""

    paid_type: PaidFactory[TPaid, TCostEnum]
    cost_type: type[TCostEnum]

    def amounts_for(self, positions: Iterable[OpenCostInvoiceLine]) -> AmountsPaid[TPaid]:
        """One amount per position that openCost can be given an amount for."""
        rows = list(positions)
        items: list[TPaid] = []
        rejected_cost_types: list[str] = []

        for position in rows:
            amount_paid = self._amount_paid(position)
            if amount_paid is None:
                # None means an unusable cost type, amount or currency; the cost type is what
                # names the position to a reader.
                rejected_cost_types.append(position.cost_type.value)
            else:
                items.append(amount_paid)

        return AmountsPaid(items, rejected_cost_types, len(rows))

    def _amount_paid(self, position: OpenCostInvoiceLine) -> TPaid | None:
        """One exported amount, or ``None`` when the position cannot be given one.

        The line's amount is already normalized through CODA's monetary calculation.
        """
        if isinstance(position.cost_type, UnmappedCostType):
            return None
        return map_or_none(
            lambda cost_type_value: self.paid_type(
                amount=position.amount_paid.amount,
                currency=position.amount_paid.currency.code,
                cost_type=self.cost_type(cost_type_value),
                vat=None if position.vat is None else position.vat.amount,
            ),
            position.cost_type.value,
        )


PUBLICATION_COST_TYPES = InvoiceCostTypes(
    paid_type=PublicationAmountPaidType,
    cost_type=PublicationCostType,
)

CONTRACT_COST_TYPES = InvoiceCostTypes(
    paid_type=ContractAmountPaidType,
    cost_type=ContractCostType,
)


def _dates_if_exportable[TPaid](
    report_item: ReportItem,
    report_invoice: LiveInvoice,
    amounts: AmountsPaid[TPaid],
) -> Dates | None:
    """The dates block, or ``None`` when this invoice may not be exported — saying why.

    openCost requires a date and at least one amount-paid element per invoice, so an invoice
    missing either is left out and reported rather than exported in a form the schema rejects.
    Rows openCost could not be given an amount for do not hold the invoice back; they are
    reported alongside the invoice that was built without them.
    """
    label = _invoice_label(report_invoice)
    dates = _invoice_dates(report_invoice.invoice_date)

    if dates is None:
        # XSD requires an invoice or payment date.
        report_item.issue(_no_invoice_date_warning_message(label))
        return None

    if not amounts.items:
        # XSD requires at least one amount_paid per invoice.
        report_item.issue(_no_positions_warning_message(label, amounts.rejected_cost_types))
        return None

    if amounts.rejected_cost_types:
        report_item.issue(
            _excluded_positions_warning_message(
                label, amounts.rejected_cost_types, amounts.row_count
            )
        )

    return dates


def _invoice_label(report_invoice: LiveInvoice) -> str:
    """Identify an invoice to a human reader."""
    return report_invoice.invoice_number or "Unnumbered invoice"


def _invoice_dates(invoice_date: date | None) -> Dates | None:
    """Return the dates block, or ``None`` when openCost would have no date at all."""
    if invoice_date is None:
        return None

    return Dates(invoice=str(invoice_date))


def _no_invoice_date_warning_message(label: str) -> str:
    return f"Invoice {label} has no invoice date and was excluded."


def _no_positions_warning_message(label: str, rejected_cost_types: list[str]) -> str:
    if not rejected_cost_types:
        return f"Invoice {label} has no positions and was excluded."

    return (
        f"Invoice {label} has no positions with a cost type or currency openCost accepts "
        f"({_quoted_values(rejected_cost_types)}) and was excluded."
    )


def _excluded_positions_warning_message(
    label: str, rejected_cost_types: list[str], number_of_report_positions: int
) -> str:
    return (
        f"Invoice {label}: {len(rejected_cost_types)} of {number_of_report_positions} positions "
        + "with a cost type or currency openCost does not accept "
        + f"({_quoted_values(rejected_cost_types)}) were excluded. "
        + "The invoice in the XML covers only its remaining positions."
    )


def _text_or_none(value: str) -> str | None:
    """Blank invoice text is reported as an absent element, not an empty one."""
    return value or None


def _quoted_values(values: Iterable[str]) -> str:
    return ", ".join(sorted(f"'{value}'" for value in set(values)))

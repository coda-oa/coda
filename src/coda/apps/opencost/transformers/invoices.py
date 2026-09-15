"""Building openCost invoice elements out of invoice rows.

An invoice is built the same way whichever kind it is: every position becomes one amount-paid
element when openCost accepts its cost type, currency and amount, while the invoice total is the
price stated on the invoice rather than the sum of those elements. The two kinds are written out
separately below; what they must agree on — when an invoice cannot be exported at all, and what
gets said about rows openCost could not be given an amount for — lives in
``_dates_if_exportable`` alone.

Rows arrive either as the report's own invoice records or as the ``LiveInvoice`` /
``LiveInvoicePosition`` views of a CODA invoice, so the same rules decide both.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Protocol

from coda.apps.opencost.issues import (
    AnyOpenCostReportItem,
    ValidationWarning,
    create_warning,
    record_issue,
)
from coda.apps.opencost.models import (
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportInvoice,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
)
from coda.coda_itertools import map_or_none
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

type AnyOpenCostInvoice = OpenCostReportInvoice | OpenCostReportContractInvoice | LiveInvoice
type AnyOpenCostInvoicePosition = (
    OpenCostReportInvoicePosition | OpenCostReportContractInvoicePosition | LiveInvoicePosition
)


@dataclass(frozen=True)
class LiveInvoice:
    """The invoice fields an openCost invoice element needs, read from a CODA invoice.

    A report invoice row carries these on itself; a CODA invoice holds them on its own fields
    and its creditor. Wrapping them keeps the invoice rules below indifferent to the source.
    """

    invoice_number: str
    creditor: str
    invoice_date: date | None


@dataclass(frozen=True)
class LiveInvoicePosition:
    """One CODA position in the shape a report invoice position row has."""

    amount: Decimal
    currency: str
    cost_type: str
    vat: Decimal | None


def publication_invoices(
    report_item: OpenCostReportPublication,
    issues: list[ValidationWarning] | None,
) -> list[PublicationInvoiceType] | None:
    invoices = []
    for report_invoice in report_item.invoices.all():
        invoice = publication_invoice(
            report_item, report_invoice, report_invoice.positions.all(), issues
        )
        if invoice is not None:
            invoices.append(invoice)

    return invoices or None


def publication_invoice(
    report_item: AnyOpenCostReportItem,
    report_invoice: AnyOpenCostInvoice,
    positions: Iterable[AnyOpenCostInvoicePosition],
    issues: list[ValidationWarning] | None,
) -> PublicationInvoiceType | None:
    """One invoice element, or ``None`` when openCost cannot be given this invoice at all."""
    rows = list(positions)
    amounts = PUBLICATION_COST_TYPES.amounts_for(rows)
    dates = _dates_if_exportable(report_item, report_invoice, issues, amounts)
    if dates is None:
        return None

    return PublicationInvoiceType(
        invoice_number=_text_or_none(report_invoice.invoice_number),
        creditor=_text_or_none(report_invoice.creditor),
        amounts_paid=PublicationAmountsPaid(amount_paid=amounts.items),
        dates=dates,
        amount_invoice=_publication_total(rows),
    )


def _publication_total(rows: Sequence[AnyOpenCostInvoicePosition]) -> AmountInvoice | None:
    """Total over every position held for this invoice.

    Every row counts, including ones openCost was given no cost type for, so the total can
    exceed the sum of the exported amounts: openCost asks for the price as stated on the
    invoice, not for the sum of its items. Currency comes from the first row, which both row
    sources order by amount; CODA stamps one currency on every position of an invoice, so
    which row is asked is moot for invoices CODA created.
    """
    if not rows:
        return None

    total_amount = sum((row.amount for row in rows), Decimal(0))
    return _amount_invoice(total_amount, rows[0].currency)


def contract_invoices(
    report_item: OpenCostReportContract,
    issues: list[ValidationWarning] | None,
) -> list[ContractInvoiceType] | None:
    invoices = []
    for report_invoice in report_item.invoices.all():
        invoice = contract_invoice(
            report_item,
            report_invoice,
            report_invoice.positions.all(),
            report_invoice.amount_invoice,
            report_invoice.amount_invoice_currency,
            issues,
        )
        if invoice is not None:
            invoices.append(invoice)

    return invoices or None


def contract_invoice(
    report_item: AnyOpenCostReportItem,
    report_invoice: AnyOpenCostInvoice,
    positions: Iterable[AnyOpenCostInvoicePosition],
    total_amount: Decimal | None,
    total_currency: str,
    issues: list[ValidationWarning] | None,
) -> ContractInvoiceType | None:
    """One contract invoice element.

    ``total_amount``/``total_currency`` is the price stated on the invoice over all its
    positions, rejected cost types included: the report's own invoice row holds the total
    computed when it was collected, the live path recomputes it from the same positions.
    """
    amounts = CONTRACT_COST_TYPES.amounts_for(positions)
    dates = _dates_if_exportable(report_item, report_invoice, issues, amounts)
    if dates is None:
        return None

    return ContractInvoiceType(
        invoice_number=_text_or_none(report_invoice.invoice_number),
        creditor=_text_or_none(report_invoice.creditor),
        amounts_paid=ContractAmountsPaid(amount_paid=amounts.items),
        dates=dates,
        amount_invoice=_amount_invoice(total_amount, total_currency),
    )


def _amount_invoice(amount: Decimal | None, currency: str) -> AmountInvoice | None:
    """The invoice total, or ``None`` when openCost cannot be given an amount and currency.

    The amount keeps the precision it arrives at; the XML writer is what formats it. An unusable
    currency is rejected by openCost's own model, which raises a ``ValueError`` subclass that
    ``map_or_none`` turns into an absent element.
    """
    return map_or_none(
        lambda currency_code: AmountInvoice(amount=amount, currency=currency_code),
        currency,
    )


class PaidFactory[TPaid, TCostEnum: Enum](Protocol):
    """Creates one openCost amount-paid element from an already accepted cost type."""

    def __call__(
        self,
        *,
        amount: Decimal,
        currency: str,
        cost_type: TCostEnum,
        vat: Decimal,
    ) -> TPaid: ...


@dataclass(frozen=True)
class AmountsPaid[TPaid]:
    """What became of an invoice's snapshot rows: the amounts, and the rows that were not."""

    items: list[TPaid]
    rejected_cost_types: list[str]
    row_count: int


@dataclass(frozen=True)
class InvoiceCostTypes[TPaid, TCostEnum: Enum]:
    """The openCost vocabulary one invoice kind maps snapshot positions onto."""

    paid_type: PaidFactory[TPaid, TCostEnum]
    cost_type: type[TCostEnum]

    def amounts_for(self, positions: Iterable[AnyOpenCostInvoicePosition]) -> AmountsPaid[TPaid]:
        """One amount per snapshot row that openCost can be given an amount for."""
        rows = list(positions)
        items: list[TPaid] = []
        rejected_cost_types: list[str] = []

        for position in rows:
            amount_paid = self._amount_paid(position)
            if amount_paid is None:
                # None means an unusable cost type, amount or currency; the cost type is what
                # names the position to a reader.
                rejected_cost_types.append(position.cost_type)
            else:
                items.append(amount_paid)

        return AmountsPaid(items, rejected_cost_types, len(rows))

    def _amount_paid(self, position: AnyOpenCostInvoicePosition) -> TPaid | None:
        """One exported amount, or ``None`` when the snapshot row cannot be given one.

        Amounts go through at the precision the snapshot holds them at, so the exported
        number is the snapshotted number and not a re-rounded copy of it.
        """
        return map_or_none(
            lambda raw_cost_type: self.paid_type(
                amount=position.amount,
                currency=position.currency,
                cost_type=self.cost_type(raw_cost_type),
                vat=position.vat or Decimal(0),
            ),
            position.cost_type,
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
    report_item: AnyOpenCostReportItem,
    report_invoice: AnyOpenCostInvoice,
    issues: list[ValidationWarning] | None,
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
        record_issue(
            issues,
            create_warning(report_item, _no_invoice_date_warning_message(label)),
        )
        return None

    if not amounts.items:
        # XSD requires at least one amount_paid per invoice.
        record_issue(
            issues,
            create_warning(
                report_item, _no_positions_warning_message(label, amounts.rejected_cost_types)
            ),
        )
        return None

    if amounts.rejected_cost_types:
        record_issue(
            issues,
            create_warning(
                report_item,
                _excluded_positions_warning_message(
                    label, amounts.rejected_cost_types, amounts.row_count
                ),
            ),
        )

    return dates


def _invoice_label(report_invoice: AnyOpenCostInvoice) -> str:
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
    """Blank snapshot text is reported as an absent element, not an empty one."""
    return value or None


def _quoted_values(values: Iterable[str]) -> str:
    return ", ".join(sorted(f"'{value}'" for value in set(values)))

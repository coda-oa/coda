"""Read model for budget balances (docs/design/budget-system.md §3).

Balances are derived from existing rows; only transfers persist budget
records. This module is the single place that computes reserved / spent /
credited / debit / available / pending conversion per budget.

Assignment amounts carry no currency of their own — the currency lives on
the position's cost. Sums are therefore grouped per cost currency: amounts
in the budget's currency count directly; foreign-currency amounts land in
the pending-conversion bucket until their bank rate is entered."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Round

from coda.apps.fundingrequests.models import ReviewFundingSplit as ReviewFundingSplitModel
from coda.apps.invoices.models import BudgetTransfer as BudgetTransferModel
from coda.apps.invoices.models import CurrencyConversion as CurrencyConversionModel
from coda.apps.invoices.models import FundingAssignment as FundingAssignmentModel
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.domain.finance.invoice import FundingSourceId, PaymentStatus
from coda.domain.money import Currency, Money


@dataclass(frozen=True)
class BudgetBalance:
    amount: Money
    reserved: Money
    spent: Money
    credited: Money
    debit: Money
    pending: tuple[Money, ...] = field(default=())

    @property
    def available(self) -> Money:
        return self.amount - self.reserved - self.spent + self.credited - self.debit


def _transfer_sum(
    *, target_id: int | None = None, source_id: int | None = None, positive: bool
) -> Decimal:
    comparison = "gt" if positive else "lt"
    filters: dict[str, object] = {f"amount__{comparison}": 0}
    if target_id is not None:
        filters["target_id"] = target_id
    if source_id is not None:
        filters["source_id"] = source_id
    result = BudgetTransferModel.objects.filter(**filters).aggregate(total=Sum("amount"))["total"]
    return result or Decimal(0)


def _gross_assignment_rows(funding_source_id: FundingSourceId) -> list[dict[str, Any]]:
    """Assignment rows aggregated per invoice, gross-of-tax: each row's amount
    × (1 + the position's tax rate), rounded per row to its cost currency's
    minor units (ROUND_HALF_UP — Postgres ROUND(numeric, n) matches
    ``Money``'s quantize). VAT-type rows self-handle: they persist rate 0 with
    the full cost in ``amount``. One query per cost currency because the
    rounding precision is the currency's, and one aggregate spans several."""
    cost_currencies = (
        FundingAssignmentModel.objects.filter(funding_source_id=funding_source_id)
        .values_list("position__cost_currency", flat=True)
        .order_by()  # default Meta ordering would leak `id` into DISTINCT
        .distinct()
    )
    rows: list[dict[str, object]] = []
    for code in cost_currencies:
        precision = Currency[code].minor_units
        gross = Round(
            F("amount") * (1 + F("position__tax_rate")),
            precision=precision,
            output_field=DecimalField(max_digits=24, decimal_places=precision),
        )
        rows += cast(
            "list[dict[str, Any]]",
            list(
                FundingAssignmentModel.objects.filter(
                    funding_source_id=funding_source_id, position__cost_currency=code
                )
                .order_by()  # default Meta ordering would leak `id` into GROUP BY and duplicate rows
                .values(
                    "position__invoice_id",
                    "position__invoice__status",
                    "position__cost_currency",
                    "position__publication__fundingrequest",
                )
                .annotate(
                    total=Sum(
                        gross, output_field=DecimalField(max_digits=24, decimal_places=precision)
                    )
                ),
            ),
        )
    return rows


def budget_balances(funding_source_id: FundingSourceId) -> BudgetBalance:
    budget = FundingSourceModel.objects.get(pk=funding_source_id)
    assert budget.budget_amount is not None
    assert budget.budget_currency is not None
    currency = Currency[budget.budget_currency]

    rows = _gross_assignment_rows(funding_source_id)
    invoice_ids = {row["position__invoice_id"] for row in rows}
    rates_to_budget_currency: dict[int, Decimal] = {
        row["invoice_id"]: row["exchange_rate"]
        for row in CurrencyConversionModel.objects.filter(
            invoice_id__in=invoice_ids, target_currency=currency.code
        ).values("invoice_id", "exchange_rate")
    }

    spent = Decimal(0)
    reserved = Decimal(0)
    pending: dict[str, Decimal] = {}
    requests_with_assignments: set[int] = set()
    for row in rows:
        total: Decimal = row["total"] or Decimal(0)
        cost_currency: str = row["position__cost_currency"]
        status: str = row["position__invoice__status"]
        request_id: int | None = row["position__publication__fundingrequest"]
        if request_id is not None:
            requests_with_assignments.add(request_id)

        if cost_currency == currency.code:
            if status == PaymentStatus.Paid.value:
                spent += total
            elif status == PaymentStatus.Unpaid.value:
                reserved += total
            continue

        rate = rates_to_budget_currency.get(row["position__invoice_id"])
        if rate is None:
            pending[cost_currency] = pending.get(cost_currency, Decimal(0)) + total
        elif status == PaymentStatus.Paid.value:
            spent += total * rate
        elif status == PaymentStatus.Unpaid.value:
            reserved += total * rate

    # Reservation precedence (budget-system.md §3): an invoice assignment for
    # a request replaces its review split — unpaid assignments count as
    # reserved, paid ones as spent (paying releases the FR reservation).
    # Splits count only for requests without any assignment on this budget.
    split_totals = (
        ReviewFundingSplitModel.objects.filter(funding_source_id=funding_source_id)
        .order_by()  # defensive: default Meta ordering would leak into GROUP BY
        .values("review__fundingrequest")
        .annotate(total=Sum("amount"))
    )
    reserved += sum(
        (
            row["total"] or Decimal(0)
            for row in split_totals
            if row["review__fundingrequest"] not in requests_with_assignments
        ),
        start=Decimal(0),
    )

    # Transfers (budget-system.md §5): available-funds transfers book debit on
    # the source and credited on the target; a debt transfer (negative amount)
    # books its overrun as debit on the target and leaves the source unchanged.
    credited = _transfer_sum(target_id=funding_source_id, positive=True)
    debit = _transfer_sum(source_id=funding_source_id, positive=True) + abs(
        _transfer_sum(target_id=funding_source_id, positive=False)
    )

    return BudgetBalance(
        amount=Money(budget.budget_amount, currency),
        reserved=Money(reserved, currency),
        spent=Money(spent, currency),
        credited=Money(credited, currency),
        debit=Money(debit, currency),
        pending=tuple(Money(total, Currency[code]) for code, total in sorted(pending.items())),
    )

"""Backfill budget accounting terms for existing budget-type funding sources.

Implements the auto-backfill contract from docs/design/budget-system.md §7:
amount = the budget's historical assignment total; period = earliest to
latest invoice date that assigned this budget in a funding assignment.
Budgets without any assignments get amount 0 and an unbounded period.

The "budget rows have amount + period" check constraint is authored in the
migration AFTER this one: applying it before the backfill would violate on
databases holding name-only budget rows created by invoice import."""

import datetime
from decimal import Decimal

from django.db import migrations, models


def backfill_budget_terms(apps, schema_editor) -> None:
    FundingSource = apps.get_model("invoices", "FundingSource")
    FundingAssignment = apps.get_model("invoices", "FundingAssignment")
    Invoice = apps.get_model("invoices", "Invoice")

    # The system-wide currency is a single setting with a EUR default
    # (budget-system.md §2); a one-time backfill does not read it across
    # app boundaries — budgets created under a different setting are rare
    # enough to correct via the budget edit surface.
    home_currency = "EUR"

    for budget in FundingSource.objects.filter(type="budget"):
        # Assignment amounts are currency-less (the currency lives on the
        # position). Sum only budget-currency assignments: foreign-currency
        # bookings stay in the read model's pending bucket and must not
        # inflate the fabricated amount (budget-system.md §3, §7).
        assignments = FundingAssignment.objects.filter(
            funding_source=budget, position__cost_currency=home_currency
        )
        total = assignments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

        assigning_invoices = Invoice.objects.filter(
            positions__funding_assignments__funding_source=budget
        ).order_by("date")
        first_date = assigning_invoices.values_list("date", flat=True).first()
        last_date = assigning_invoices.values_list("date", flat=True).last()

        budget.budget_amount = total
        budget.budget_currency = home_currency
        budget.period_start = first_date or datetime.date.min
        budget.period_end = last_date or datetime.date.max
        budget.save(update_fields=["budget_amount", "budget_currency", "period_start", "period_end"])


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0028_budgetledgerentry"),
    ]

    operations = [
        migrations.RunPython(backfill_budget_terms, migrations.RunPython.noop),
    ]

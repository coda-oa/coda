from decimal import Decimal

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestBackfillBudgetTerms(MigratorTestCase):
    """Auto-backfill contract: amount = historical assignment total; period =
    earliest → latest assigning-invoice date; budgets without assignments get
    0 and an unbounded period; the constraint (0030) applies only after the
    backfill."""

    migrate_from = ("invoices", "0025_alter_fundingassignment_options")
    migrate_to = ("invoices", "0030_fundingsource_budget_type_has_amount_and_period")

    def prepare(self) -> None:
        Creditor = self.old_state.apps.get_model("invoices", "Creditor")
        Invoice = self.old_state.apps.get_model("invoices", "Invoice")
        FundingSource = self.old_state.apps.get_model("invoices", "FundingSource")
        Position = self.old_state.apps.get_model("invoices", "Position")
        FundingAssignment = self.old_state.apps.get_model("invoices", "FundingAssignment")

        creditor = Creditor.objects.create(name="Test Creditor")
        invoice_march = Invoice.objects.create(
            number="INV-03", date="2025-03-01", creditor=creditor, status="paid"
        )
        invoice_june = Invoice.objects.create(
            number="INV-06", date="2025-06-15", creditor=creditor, status="paid"
        )

        assigned_budget = FundingSource.objects.create(name="Assigned Budget", type="budget")
        empty_budget = FundingSource.objects.create(name="Empty Budget", type="budget")
        usd_budget = FundingSource.objects.create(name="USD Budget", type="budget")
        institution_source = FundingSource.objects.create(
            name="Institution Source", type="institution"
        )

        for invoice, amount in (
            (invoice_march, Decimal("100.50")),
            (invoice_june, Decimal("75.00")),
        ):
            position = Position.objects.create(
                invoice=invoice,
                description="APC",
                cost_amount=amount,
                cost_currency="EUR",
            )
            FundingAssignment.objects.create(
                position=position, funding_source=assigned_budget, amount=amount
            )

        usd_invoice = Invoice.objects.create(
            number="INV-04", date="2025-04-10", creditor=creditor, status="paid"
        )
        usd_position = Position.objects.create(
            invoice=usd_invoice,
            description="APC (USD)",
            cost_amount=Decimal("3000.00"),
            cost_currency="USD",
        )
        FundingAssignment.objects.create(
            position=usd_position, funding_source=usd_budget, amount=Decimal("3000.00")
        )

        self.assigned_budget_pk = assigned_budget.pk
        self.empty_budget_pk = empty_budget.pk
        self.usd_budget_pk = usd_budget.pk
        self.institution_source_pk = institution_source.pk

    def test_assigned_budget_gets_assignment_total_and_invoice_period(self) -> None:
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")
        budget = FundingSource.objects.get(pk=self.assigned_budget_pk)

        assert budget.budget_amount == Decimal("175.50")
        assert budget.budget_currency == "EUR"
        assert str(budget.period_start) == "2025-03-01"
        assert str(budget.period_end) == "2025-06-15"

    def test_empty_budget_gets_zero_and_unbounded_period(self) -> None:
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")
        budget = FundingSource.objects.get(pk=self.empty_budget_pk)

        assert budget.budget_amount == Decimal(0)
        assert str(budget.period_start) == "0001-01-01"
        assert str(budget.period_end) == "9999-12-31"

    def test_foreign_currency_assignments_are_excluded_from_the_fabricated_amount(self) -> None:
        """The read model keeps foreign-currency bookings in the pending
        bucket, excluded from balances — the backfill must not fabricate an
        amount from them (it would overstate exactly that amount)."""
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")
        budget = FundingSource.objects.get(pk=self.usd_budget_pk)

        assert budget.budget_amount == Decimal(0)
        assert str(budget.period_start) == "2025-04-10"
        assert str(budget.period_end) == "2025-04-10"

    def test_institution_source_stays_untouched(self) -> None:
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")
        source = FundingSource.objects.get(pk=self.institution_source_pk)

        assert source.budget_amount is None
        assert source.budget_currency is None
        assert source.period_start is None
        assert source.period_end is None

    def test_constraint_applies_after_backfill_without_violation(self) -> None:
        """The suite's migrate_to already ran the constraint migration (0030)
        on top of the backfill — with name-only budget rows seeded before the
        columns existed. Reaching this test proves the deferral ordering."""
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")
        assert FundingSource.objects.filter(type="budget").count() == 3

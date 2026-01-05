from decimal import Decimal

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestRemovePositionFundingSourceReverse(MigratorTestCase):
    """Test reverse migration: Restore position.funding_source from assignments."""

    migrate_from = ("invoices", "0021_remove_position_funding_source")
    migrate_to = ("invoices", "0020_migrate_funding_source_to_assignments")

    def prepare(self) -> None:
        """Create all test data before reverse migration."""
        Creditor = self.old_state.apps.get_model("invoices", "Creditor")
        Invoice = self.old_state.apps.get_model("invoices", "Invoice")
        FundingSource = self.old_state.apps.get_model("invoices", "FundingSource")
        Position = self.old_state.apps.get_model("invoices", "Position")
        FundingAssignment = self.old_state.apps.get_model("invoices", "FundingAssignment")

        creditor = Creditor.objects.create(name="Test Creditor")
        invoice = Invoice.objects.create(
            number="INV-001",
            date="2025-01-01",
            creditor=creditor,
            status="Unpaid",
        )

        budget_a = FundingSource.objects.create(name="Budget A", type="budget")
        budget_b = FundingSource.objects.create(name="Budget B", type="budget")
        institution_fund = FundingSource.objects.create(
            name="Institution Fund",
            type="institution",
        )

        self.budget_a_pk = budget_a.pk
        self.budget_b_pk = budget_b.pk

        self.position_single_budget = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("100.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            description="Position with single budget assignment",
        )
        FundingAssignment.objects.create(
            position=self.position_single_budget,
            funding_source=budget_a,
            amount=Decimal("100.00"),
        )

        self.position_only_institution = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("200.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            description="Position with only institution assignment",
        )
        FundingAssignment.objects.create(
            position=self.position_only_institution,
            funding_source=institution_fund,
            amount=Decimal("200.00"),
        )

        self.position_mixed = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("150.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            description="Position with mixed assignments",
        )
        FundingAssignment.objects.create(
            position=self.position_mixed,
            funding_source=institution_fund,
            amount=Decimal("100.00"),
        )
        FundingAssignment.objects.create(
            position=self.position_mixed,
            funding_source=budget_a,
            amount=Decimal("50.00"),
        )

        self.position_institution_first = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("300.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            description="Position with institution created before budget",
        )
        FundingAssignment.objects.create(
            position=self.position_institution_first,
            funding_source=institution_fund,
            amount=Decimal("250.00"),
        )
        FundingAssignment.objects.create(
            position=self.position_institution_first,
            funding_source=budget_b,
            amount=Decimal("50.00"),
        )

        self.position_no_assignments = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("50.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            description="Position without assignments",
        )

        self.position_multiple_budgets = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("400.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            description="Position with multiple budget assignments",
        )
        FundingAssignment.objects.create(
            position=self.position_multiple_budgets,
            funding_source=budget_a,
            amount=Decimal("300.00"),
        )
        FundingAssignment.objects.create(
            position=self.position_multiple_budgets,
            funding_source=budget_b,
            amount=Decimal("100.00"),
        )

    def test_restores_funding_source_from_budget_assignment(self) -> None:
        """Verify reverse migration restores funding_source from budget assignment."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_single_budget.pk)
        assert pos.funding_source_id == self.budget_a_pk

    def test_leaves_null_when_only_institution_assignments_exist(self) -> None:
        """Verify position.funding_source stays NULL when only institution sources exist."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_only_institution.pk)
        assert pos.funding_source_id is None

    def test_restores_first_budget_source_ignoring_institutions(self) -> None:
        """Verify reverse migration uses first budget source, skipping institution sources."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_mixed.pk)
        assert pos.funding_source_id == self.budget_a_pk

    def test_restores_budget_source_even_when_institution_created_first(self) -> None:
        """Verify reverse migration uses budget source regardless of creation order."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_institution_first.pk)
        assert pos.funding_source_id == self.budget_b_pk

    def test_leaves_null_when_no_assignments_exist(self) -> None:
        """Verify positions without assignments get NULL funding_source."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_no_assignments.pk)
        assert pos.funding_source_id is None

    def test_handles_multiple_budget_assignments(self) -> None:
        """Verify reverse migration uses first budget assignment when multiple exist."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_multiple_budgets.pk)
        assert pos.funding_source_id == self.budget_a_pk

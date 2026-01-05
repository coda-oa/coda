from decimal import Decimal
from typing import Any

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestMigrateFundingSourceToAssignmentsForward(MigratorTestCase):
    """Forward migration tests: Position.funding_source → FundingAssignment."""

    migrate_from = ("invoices", "0019_alter_fundingassignment_funding_source")
    migrate_to = ("invoices", "0020_migrate_funding_source_to_assignments")

    def prepare(self) -> None:
        """Create all test data before migration."""
        Creditor = self.old_state.apps.get_model("invoices", "Creditor")
        Invoice = self.old_state.apps.get_model("invoices", "Invoice")
        FundingSource = self.old_state.apps.get_model("invoices", "FundingSource")

        creditor = Creditor.objects.create(name="Test Creditor")
        invoice = Invoice.objects.create(
            number="INV-001",
            date="2025-01-01",
            creditor=creditor,
            status="Unpaid",
        )

        budget_a = FundingSource.objects.create(name="Budget A", type="budget")
        budget_b = FundingSource.objects.create(name="Budget B", type="budget")
        budget_c = FundingSource.objects.create(name="Budget C", type="budget")

        self.position_to_migrate = self._create_position(
            invoice,
            cost_amount=Decimal("100.50"),
            funding_source=budget_a,
        )
        self.budget_a_pk = budget_a.pk

        self.position_null_funding = self._create_position(
            invoice,
            cost_amount=Decimal("200.00"),
            cost_currency="USD",
            funding_source=None,
        )

        self.position_multiple_1 = self._create_position(
            invoice,
            cost_amount=Decimal("50.25"),
            cost_currency="GBP",
            funding_source=budget_b,
        )
        self.budget_b_pk = budget_b.pk

        self.position_multiple_2 = self._create_position(
            invoice,
            cost_amount=Decimal("75.00"),
            funding_source=budget_c,
        )
        self.budget_c_pk = budget_c.pk

        self.position_already_has_assignment = self._create_position(
            invoice,
            cost_amount=Decimal("150.00"),
            funding_source=budget_a,
        )
        FundingAssignment = self.old_state.apps.get_model("invoices", "FundingAssignment")
        FundingAssignment.objects.create(
            position=self.position_already_has_assignment,
            funding_source=budget_a,
            amount=Decimal("150.00"),
        )

        self.position_zero_amount = self._create_position(
            invoice,
            cost_amount=Decimal("0.00"),
            funding_source=budget_a,
        )

        self.position_negative_amount = self._create_position(
            invoice,
            cost_amount=Decimal("-50.00"),
            funding_source=budget_b,
        )

        self.position_large_decimal = self._create_position(
            invoice,
            cost_amount=Decimal("999999.9999"),
            funding_source=budget_c,
        )

    def _create_position(
        self,
        invoice: Any,
        cost_amount: Decimal,
        funding_source: Any,
        cost_currency: str = "EUR",
    ) -> Any:
        """Helper to create positions with common defaults."""
        Position = self.old_state.apps.get_model("invoices", "Position")
        return Position.objects.create(
            invoice=invoice,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            funding_source=funding_source,
            description="Test position",
        )

    def test_creates_assignment_for_position_with_funding_source(self) -> None:
        """Verify migration creates FundingAssignment for position with funding_source."""
        FundingAssignment = self.new_state.apps.get_model("invoices", "FundingAssignment")
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_to_migrate.pk)
        assignments = FundingAssignment.objects.filter(position=pos)

        assert assignments.count() == 1
        assignment = assignments.first()
        assert assignment is not None
        assert assignment.funding_source_id == self.budget_a_pk
        assert assignment.amount == Decimal("100.50")

    def test_skips_positions_with_null_funding_source(self) -> None:
        """Verify migration skips positions with NULL funding_source."""
        FundingAssignment = self.new_state.apps.get_model("invoices", "FundingAssignment")
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_null_funding.pk)
        assignments = FundingAssignment.objects.filter(position=pos)

        assert assignments.count() == 0

    def test_handles_multiple_positions(self) -> None:
        """Verify migration handles multiple positions correctly."""
        FundingAssignment = self.new_state.apps.get_model("invoices", "FundingAssignment")
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos_1 = Position.objects.get(pk=self.position_multiple_1.pk)
        assignments_1 = FundingAssignment.objects.filter(position=pos_1)
        assert assignments_1.count() == 1
        assert assignments_1.first().funding_source_id == self.budget_b_pk
        assert assignments_1.first().amount == Decimal("50.25")

        pos_2 = Position.objects.get(pk=self.position_multiple_2.pk)
        assignments_2 = FundingAssignment.objects.filter(position=pos_2)
        assert assignments_2.count() == 1
        assert assignments_2.first().funding_source_id == self.budget_c_pk
        assert assignments_2.first().amount == Decimal("75.00")

    def test_is_idempotent(self) -> None:
        """Verify migration doesn't create duplicate assignments."""
        FundingAssignment = self.new_state.apps.get_model("invoices", "FundingAssignment")
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_already_has_assignment.pk)
        assignments = FundingAssignment.objects.filter(position=pos)

        assert assignments.count() == 1
        assert assignments.first().funding_source_id == self.budget_a_pk
        assert assignments.first().amount == Decimal("150.00")

    def test_preserves_original_field(self) -> None:
        """Verify migration does NOT remove the old funding_source field value."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_to_migrate.pk)
        assert pos.funding_source_id == self.budget_a_pk

    def test_handles_edge_case_amounts(self) -> None:
        """Verify migration handles zero, negative, and large amounts correctly."""
        FundingAssignment = self.new_state.apps.get_model("invoices", "FundingAssignment")
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos_zero = Position.objects.get(pk=self.position_zero_amount.pk)
        assignments_zero = FundingAssignment.objects.filter(position=pos_zero)
        assert assignments_zero.count() == 1
        assert assignments_zero.first().amount == Decimal("0.00")

        pos_negative = Position.objects.get(pk=self.position_negative_amount.pk)
        assignments_negative = FundingAssignment.objects.filter(position=pos_negative)
        assert assignments_negative.count() == 1
        assert assignments_negative.first().amount == Decimal("-50.00")

        pos_large = Position.objects.get(pk=self.position_large_decimal.pk)
        assignments_large = FundingAssignment.objects.filter(position=pos_large)
        assert assignments_large.count() == 1
        assert assignments_large.first().amount == Decimal("999999.9999")


@pytest.mark.django_db
class TestMigrateFundingSourceToAssignmentsReverse(MigratorTestCase):
    """Reverse migration tests: Delete FundingAssignment records."""

    migrate_from = ("invoices", "0020_migrate_funding_source_to_assignments")
    migrate_to = ("invoices", "0019_alter_fundingassignment_funding_source")

    def prepare(self) -> None:
        """Create all test data before reverse migration."""
        Creditor = self.old_state.apps.get_model("invoices", "Creditor")
        Invoice = self.old_state.apps.get_model("invoices", "Invoice")
        FundingSource = self.old_state.apps.get_model("invoices", "FundingSource")
        Position = self.old_state.apps.get_model("invoices", "Position")
        FundingAssignment = self.old_state.apps.get_model("invoices", "FundingAssignment")

        creditor = Creditor.objects.create(name="Test Creditor Rev")
        invoice = Invoice.objects.create(
            number="INV-REV-001",
            date="2025-01-01",
            creditor=creditor,
            status="Unpaid",
        )

        budget_x = FundingSource.objects.create(name="Budget X", type="budget")
        self.budget_x_pk = budget_x.pk

        self.position_with_assignment = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("100.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            funding_source=budget_x,
            description="Position with funding source and assignment",
        )
        FundingAssignment.objects.create(
            position=self.position_with_assignment,
            funding_source=budget_x,
            amount=Decimal("100.00"),
        )

        self.position_another_assignment = Position.objects.create(
            invoice=invoice,
            cost_amount=Decimal("200.00"),
            cost_currency="EUR",
            cost_type="Publication_Charge",
            tax_rate=Decimal("19.0"),
            funding_source=budget_x,
            description="Another position with assignment",
        )
        FundingAssignment.objects.create(
            position=self.position_another_assignment,
            funding_source=budget_x,
            amount=Decimal("200.00"),
        )

    def test_preserves_funding_source_during_reverse(self) -> None:
        """Verify reverse migration doesn't modify position.funding_source field."""
        Position = self.new_state.apps.get_model("invoices", "Position")

        pos = Position.objects.get(pk=self.position_with_assignment.pk)
        assert pos.funding_source_id == self.budget_x_pk

    def test_deletes_all_assignments(self) -> None:
        """Verify reverse migration deletes ALL assignments."""
        FundingAssignment = self.new_state.apps.get_model("invoices", "FundingAssignment")

        assert FundingAssignment.objects.count() == 0

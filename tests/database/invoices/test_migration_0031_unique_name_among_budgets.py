import pytest
from django.db import IntegrityError
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestUniqueNameAmongBudgets(MigratorTestCase):
    """The partial unique constraint (0031) applies only to budget-type
    funding sources; the migration's loud pre-check refuses to apply it over
    data that already violates it (docs/design/budget-system-test-plan.md,
    cost-basis amendment)."""

    migrate_from = ("invoices", "0030_fundingsource_budget_type_has_amount_and_period")
    migrate_to = ("invoices", "0031_unique_name_among_budgets")

    def prepare(self) -> None:
        FundingSource = self.old_state.apps.get_model("invoices", "FundingSource")
        Institution = self.old_state.apps.get_model("institutions", "Institution")

        institution = Institution.objects.create(name="Test Institution")
        self.budget_pk = FundingSource.objects.create(
            type="budget",
            name="DARK 2026",
            budget_amount=10000,
            budget_currency="EUR",
            period_start="2026-01-01",
            period_end="2026-12-31",
        ).pk
        self.institution_pk = FundingSource.objects.create(
            type="institution", name="DARK 2026", institution_id=institution.pk
        ).pk

    def test_constraint_rejects_duplicate_budget_names(self) -> None:
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")

        with pytest.raises(IntegrityError):
            FundingSource.objects.create(
                type="budget",
                name="DARK 2026",
                budget_amount=1000,
                budget_currency="EUR",
                period_start="2026-01-01",
                period_end="2026-12-31",
            )

    def test_institution_sources_are_unaffected(self) -> None:
        FundingSource = self.new_state.apps.get_model("invoices", "FundingSource")
        Institution = self.new_state.apps.get_model("institutions", "Institution")

        institution = Institution.objects.create(name="Other Institution")
        FundingSource.objects.create(
            type="institution", name="DARK 2026", institution_id=institution.pk
        )

        assert FundingSource.objects.filter(name="DARK 2026", type="institution").count() == 2
        assert (
            self.new_state.apps.get_model("invoices", "FundingSource")
            .objects.get(pk=self.budget_pk)
            .name
            == "DARK 2026"
        )


def test_pre_check_fails_loudly_on_duplicate_budget_names(db) -> None:
    """The pre-check function refuses to let the constraint apply over data
    that already violates it — loudly, without inventing a rename policy."""
    import importlib

    from django.db import connection

    from coda.apps.invoices.models import FundingSource

    migration = importlib.import_module(
        "coda.apps.invoices.migrations.0031_unique_name_among_budgets"
    )

    # The test database is already migrated to head. A conditional
    # UniqueConstraint is implemented by Django as a partial unique INDEX
    # (Postgres table constraints cannot be conditional), so drop the index
    # to reconstruct the pre-migration state the check guards against.
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS unique_name_among_budgets")
    for _ in range(2):
        FundingSource.objects.create(
            type="budget",
            name="DARK 2026",
            budget_amount=10000,
            budget_currency="EUR",
            period_start="2026-01-01",
            period_end="2026-12-31",
        )

    class _Apps:
        @staticmethod
        def get_model(label: str, model: str) -> type[FundingSource]:
            return FundingSource

    with pytest.raises(RuntimeError, match="share names"):
        migration.fail_on_duplicate_budget_names(_Apps(), None)

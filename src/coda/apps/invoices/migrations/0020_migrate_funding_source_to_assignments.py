# Migration to convert Position.funding_source to FundingAssignment records

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def migrate_funding_sources_to_assignments(apps, schema_editor):
    """
    Migrate Position.funding_source to FundingAssignment records.

    For each Position with:
    - funding_source IS NOT NULL
    - No existing funding_assignments

    Create one FundingAssignment with amount = position.cost_amount
    """
    Position = apps.get_model("invoices", "Position")
    FundingAssignment = apps.get_model("invoices", "FundingAssignment")

    # Query positions to migrate
    positions_to_migrate = Position.objects.filter(
        funding_source__isnull=False
    ).prefetch_related("funding_assignments")

    assignments_to_create = []
    migrated_count = 0
    skipped_count = 0

    for position in positions_to_migrate:
        # Skip if already has assignments (idempotency)
        if position.funding_assignments.exists():
            skipped_count += 1
            continue

        # Create assignment with full cost (preserves zero/negative)
        assignments_to_create.append(
            FundingAssignment(
                position=position,
                funding_source=position.funding_source,
                amount=position.cost_amount,
            )
        )
        migrated_count += 1

    # Bulk create for performance
    if assignments_to_create:
        FundingAssignment.objects.bulk_create(assignments_to_create)

    # Log results
    logger.info(
        f"Funding source migration complete: "
        f"Migrated {migrated_count} positions, "
        f"Skipped {skipped_count} positions (already have assignments)"
    )


def reverse_migration(apps, schema_editor):
    """
    Reverse migration: Delete all FundingAssignment records.

    The forward migration preserves position.funding_source values,
    so no restoration is needed. This simply removes all assignments
    to revert to the funding_source-only system.
    """
    FundingAssignment = apps.get_model("invoices", "FundingAssignment")

    deleted_count, _ = FundingAssignment.objects.all().delete()

    logger.info(f"Reverse migration complete: Deleted {deleted_count} assignments")


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0019_alter_fundingassignment_funding_source"),
    ]

    operations = [
        migrations.RunPython(
            migrate_funding_sources_to_assignments,
            reverse_code=reverse_migration,
        ),
    ]

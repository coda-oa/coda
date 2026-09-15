import logging

from django.db import transaction

from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.services.queries import load_transform_tree
from coda.apps.opencost.transformers import to_opencost

logger = logging.getLogger(__name__)


def collect_issues(report: OpenCostReport) -> list[ValidationWarning] | None:
    """What exporting this snapshot would do, and what it would cost. None on failure."""
    issues: list[ValidationWarning] = []
    try:
        with transaction.atomic():  # savepoint: ATOMIC_REQUESTS is on
            publications, contracts = load_transform_tree(report)
            to_opencost(report, publications, contracts, issues)
            return issues
    except Exception:  # a broken panel must never take anything down
        logger.exception("openCost data completeness check failed for report %s", report.pk)
        return None

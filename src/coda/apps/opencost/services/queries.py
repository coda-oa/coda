from django.db.models import Prefetch, QuerySet

from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportPublication,
)

PUBLICATION_PREFETCHES = (
    "institution_identifiers",
    "links",
    "linked_contracts__contract__links__type",
    "invoices__positions",
    "publication__fundingrequest",
)
CONTRACT_PREFETCHES = (
    "contract",
    "institution_identifiers",
    "secondary_identifiers",
    "invoices__positions",
)


def transform_ready_reports() -> QuerySet[OpenCostReport]:
    """Report queryset prefetched so transformers never triggers a query."""
    return OpenCostReport.objects.prefetch_related(
        Prefetch(
            "publications",
            queryset=OpenCostReportPublication.objects.select_related(
                "publication__fundingrequest"
            ).prefetch_related(*PUBLICATION_PREFETCHES),
        ),
        Prefetch(
            "contracts",
            queryset=OpenCostReportContract.objects.select_related(
                "contract", "report"
            ).prefetch_related(*CONTRACT_PREFETCHES),
        ),
    )


def load_transform_tree(
    report: OpenCostReport,
) -> tuple[list[OpenCostReportPublication], list[OpenCostReportContract]]:
    """Children with the shared prefetches applied, materialised. Cache-aware: when the report was
    loaded through `transform_ready_reports()`, return the populated `_prefetched_objects_cache`
    children instead of re-prefetching (joins gate below)."""
    if getattr(report, "_prefetched_objects_cache", None):
        return list(report.publications.all()), list(report.contracts.all())
    return (
        list(report.publications.prefetch_related(*PUBLICATION_PREFETCHES)),
        list(report.contracts.prefetch_related(*CONTRACT_PREFETCHES)),
    )

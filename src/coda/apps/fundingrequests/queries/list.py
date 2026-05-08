"""Query functions for funding request list view.

Implements CQRS-lite pattern with optimized bulk queries to avoid N+1 problem.
"""

from django.db.models import QuerySet

from coda.apps.fundingrequests.mappers._list import FundingRequestListMapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.queries.models import FundingRequestListItem
from coda.apps.publications.services import publications
from coda.domain.publication import PublicationId


def get_list_items(queryset: QuerySet[FundingRequestModel]) -> list[FundingRequestListItem]:
    """Convert Django queryset to list items with optimized bulk queries.

    Performance: ~3-5 queries total regardless of result count.

    Query breakdown:
    1. Input queryset (already optimized with select_related/prefetch)
    2. Bulk fetch payments for all publications

    Args:
        queryset: Pre-filtered queryset from search/filter logic

    Returns:
        List of FundingRequestListItem ready for template rendering
    """
    fr_models = list(queryset)

    if not fr_models:
        return []

    publication_ids = [PublicationId(fr.publication.id) for fr in fr_models]
    payment_statuses = publications.get_payment_statuses(publication_ids)

    return [
        FundingRequestListMapper.map(
            fr_model,
            payment_statuses[PublicationId(fr_model.publication.id)],
        )
        for fr_model in fr_models
    ]

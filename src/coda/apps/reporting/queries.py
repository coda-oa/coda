"""The ORM fetch, scoped to the filtered requests (plan §4)."""

from collections.abc import Sequence

from django.db.models import QuerySet

from coda.apps.exports.services.fundingrequest_csv import queries as export_queries
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.models import FundingRequest


def fetch_requests(
    criteria: Sequence[fundingrequest_query.FundingRequestSearchCriteria],
) -> QuerySet[FundingRequest]:
    """The filtered funding requests, with the shared export fetch shape.

    The statistics page reports over the same rows the CSV export reports
    over, so the fetch — criteria, select_related and the whole prefetch
    graph — is delegated to the export module instead of being restated here.
    """
    return export_queries.fetch_funding_requests(criteria)

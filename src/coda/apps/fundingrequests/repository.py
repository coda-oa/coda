from collections.abc import Iterable

from django.db.models import Q

from coda.apps.fundingrequests.models import FundingOrganization, FundingRequest


def search(
    *,
    title: str | None = None,
    submitter: str | None = None,
    processing_states: list[str] | None = None,
    labels: Iterable[int] | None = None,
) -> Iterable[FundingRequest]:
    query = Q()
    if title:
        query = query & Q(publication__title__icontains=title)

    if submitter:
        query = query & Q(submitter__name__icontains=submitter)

    if processing_states:
        query = query & Q(processing_status__in=processing_states)

    if labels:
        query = query & Q(labels__in=labels)

    return FundingRequest.objects.filter(query).distinct().order_by("-created_at")


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)

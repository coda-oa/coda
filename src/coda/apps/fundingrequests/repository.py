from django.db.models import Q
from collections.abc import Iterable

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.models import Publication


def create(submitter: Author, publication: Publication, funding: FundingDto) -> FundingRequest:
    return FundingRequest.objects.create(submitter=submitter, publication=publication, **funding)


def get_by_pk(pk: int) -> FundingRequest:
    return FundingRequest.objects.get(pk=pk)


def search(
    *,
    title: str | None = None,
    processing_states: list[str] | None = None,
    labels: Iterable[int] | None = None,
) -> Iterable[FundingRequest]:
    query = Q()
    if title:
        query = query & Q(publication__title__icontains=title)

    if processing_states:
        query = query & Q(processing_status__in=processing_states)

    if labels:
        query = query & Q(labels__in=labels)

    return FundingRequest.objects.filter(query).distinct().order_by("-created_at")

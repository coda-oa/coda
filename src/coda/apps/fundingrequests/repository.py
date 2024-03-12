from collections.abc import Iterable

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.models import Publication


def create(submitter: Author, publication: Publication, funding: FundingDto) -> FundingRequest:
    return FundingRequest.objects.create(submitter=submitter, publication=publication, **funding)


def get_by_pk(pk: int) -> FundingRequest:
    return FundingRequest.objects.get(pk=pk)


def search_by_publication_title(title: str) -> Iterable[FundingRequest]:
    return FundingRequest.objects.filter(publication__title__icontains=title)

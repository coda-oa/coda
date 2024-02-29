from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.models import Publication


def create(submitter: Author, publication: Publication, funding: FundingDto) -> FundingRequest:
    return FundingRequest.objects.create(submitter=submitter, publication=publication, **funding)


def get_by_id(funding_request_id: int) -> FundingRequest:
    return FundingRequest.objects.get(pk=funding_request_id)

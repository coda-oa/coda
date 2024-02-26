from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.models import Publication


def create(submitter: Author, publication: Publication, funding: FundingDto) -> FundingRequest:
    return FundingRequest.objects.create(submitter=submitter, publication=publication, **funding)

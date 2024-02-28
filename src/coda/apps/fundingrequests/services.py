from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.services import author_create
from coda.apps.fundingrequests import repository as fundinqrequest_repository
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals import repository as journal_repository
from coda.apps.publications import repository as publication_repository
from coda.apps.publications.dto import PublicationDto


def fundingrequest_create(
    author: AuthorDto, publication: PublicationDto, funding: FundingDto
) -> FundingRequest:
    _author = author_create(author)
    _journal = journal_repository.get_by_id(publication["journal"])
    _publication = publication_repository.create(publication, _author, _journal)
    return fundinqrequest_repository.create(_author, _publication, funding)

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.services import author_create
from coda.apps.fundingrequests import repository as fundinqrequest_repository
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.journals import repository as journal_repository
from coda.apps.publications import repository as publication_repository
from coda.apps.publications.dto import PublicationDto
from coda.color import Color


def fundingrequest_create(
    author: AuthorDto, publication: PublicationDto, funding: FundingDto
) -> FundingRequest:
    _author = author_create(author)
    _journal = journal_repository.get_by_id(publication["journal"])
    _publication = publication_repository.create(publication, _author, _journal)
    return fundinqrequest_repository.create(_author, _publication, funding)


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_attach(funding_request: FundingRequest, label_id: int) -> None:
    label = Label.objects.get(pk=label_id)
    funding_request.labels.add(label)
    funding_request.save()

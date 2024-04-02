from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.services import author_create
from coda.apps.fundingrequests import repository as fundinqrequest_repository
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import ExternalFunding, FundingRequest, Label
from coda.apps.journals import repository as journal_repository
from coda.apps.publications import repository as publication_repository
from coda.apps.publications.dto import PublicationDto
from coda.color import Color


def fundingrequest_create(
    author: AuthorDto,
    publication: PublicationDto,
    external_funding: ExternalFundingDto,
    cost: CostDto,
) -> FundingRequest:
    _author = author_create(author)
    _journal = journal_repository.get_by_pk(publication["journal"])
    _publication = publication_repository.create(publication, _author, _journal)
    _external_funding = external_funding_create(external_funding)
    return fundinqrequest_repository.create(_author, _publication, _external_funding, cost)


def external_funding_create(external_funding: ExternalFundingDto) -> ExternalFunding:
    return ExternalFunding.objects.create(
        organization=fundinqrequest_repository.get_funding_organization(
            external_funding["organization"]
        ),
        project_id=external_funding["project_id"],
        project_name=external_funding["project_name"],
    )


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_attach(funding_request_id: int, label_id: int) -> None:
    label = Label.objects.get(pk=label_id)
    funding_request = fundinqrequest_repository.get_by_pk(funding_request_id)
    funding_request.labels.add(label)
    funding_request.save()


def label_detach(funding_request_id: int, label_id: int) -> None:
    funding_request = fundinqrequest_repository.get_by_pk(funding_request_id)
    label = Label.objects.get(pk=label_id)
    funding_request.labels.remove(label)
    funding_request.save()

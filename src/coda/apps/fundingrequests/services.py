from django.db import transaction

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.services import author_create
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import ExternalFunding, FundingRequest, Label
from coda.apps.journals import services as journal_services
from coda.apps.publications import services as publication_services
from coda.apps.publications.dto import PublicationDto
from coda.color import Color


@transaction.atomic
def fundingrequest_create(
    author: AuthorDto,
    publication: PublicationDto,
    external_funding: ExternalFundingDto | None,
    cost: CostDto,
) -> FundingRequest:
    _author = author_create(author)
    _journal = journal_services.get_by_pk(publication["journal"])
    _publication = publication_services.publication_create(publication, _author, _journal)
    _external_funding = external_funding_or_none(external_funding)
    return FundingRequest.objects.create(
        submitter=_author, publication=_publication, external_funding=_external_funding, **cost
    )


def external_funding_or_none(external_funding: ExternalFundingDto | None) -> ExternalFunding | None:
    if external_funding:
        _external_funding = external_funding_create(external_funding)
    else:
        _external_funding = None
    return _external_funding


@transaction.atomic
def fundingrequest_funding_update(
    funding_request: FundingRequest, funding: ExternalFundingDto | None, cost: CostDto
) -> None:
    if funding_request.external_funding:
        funding_request.external_funding.delete()
        funding_request.refresh_from_db()

    if funding:
        funding_request.external_funding = external_funding_create(funding)

    funding_request.estimated_cost = cost["estimated_cost"]
    funding_request.estimated_cost_currency = cost["estimated_cost_currency"]
    funding_request.payment_method = cost["payment_method"]
    funding_request.save()


def external_funding_create(external_funding: ExternalFundingDto) -> ExternalFunding:
    return ExternalFunding.objects.create(
        organization=fundingrequest_repository.get_funding_organization(
            external_funding["organization"]
        ),
        project_id=external_funding["project_id"],
        project_name=external_funding["project_name"],
    )


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_attach(funding_request: FundingRequest, label: Label) -> None:
    funding_request.labels.add(label)
    funding_request.save()


def label_detach(funding_request: FundingRequest, label: Label) -> None:
    funding_request.labels.remove(label)
    funding_request.save()

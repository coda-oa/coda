import datetime
from collections.abc import Iterable
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.authors.models import Author
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.models import ExternalFunding, Label
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.models import Link, Publication
from coda.money import Currency, Money

template_name = "fundingrequests/fundingrequest_detail.html"


class RequestViewModel(NamedTuple):
    id: int
    request_id: str
    labels: Iterable[Label]
    created_at: datetime.date
    updated_at: datetime.date
    estimated_cost: Money


class SubmitterViewModel(NamedTuple):
    id: int
    name: str
    affiliation: str
    roles: Iterable[str]


class PublicationViewModel(NamedTuple):
    title: str
    authors: Iterable[str]
    journal_title: str
    publisher_name: str
    publication_status: str
    publication_date: datetime.date | None
    license: str
    oa_type: str
    references: Iterable[Link]
    contracts: Iterable[Contract]


class ExternalFundingViewModel(NamedTuple):
    organization: str
    project_id: str
    project_name: str


def request_viewmodel(fr: FundingRequestModel) -> RequestViewModel:
    return RequestViewModel(
        id=fr.id,
        request_id=fr.request_id,
        labels=fr.labels.all(),
        created_at=fr.created_at,
        updated_at=fr.updated_at,
        estimated_cost=Money(fr.estimated_cost, Currency[fr.estimated_cost_currency]),
    )


def submitter_viewmodel(submitter: Author) -> SubmitterViewModel:
    return SubmitterViewModel(
        id=submitter.id,
        name=submitter.name,
        affiliation=submitter.affiliation.name if submitter.affiliation else "",
        roles=[r.value for r in submitter.get_roles()],
    )


def publication_viewmodel(publication: Publication) -> PublicationViewModel:
    return PublicationViewModel(
        title=publication.title,
        authors=list(publication.authors),
        journal_title=publication.journal.title,
        publisher_name=publication.journal.publisher.name,
        publication_status=publication.publication_state,
        publication_date=publication.publication_date,
        license=publication.license,
        oa_type=publication.open_access_type,
        references=publication.links.all(),
        contracts=publication.journal.publisher.contracts.all(),
    )


def funding_viewmodel(external_funding: ExternalFunding) -> ExternalFundingViewModel:
    return ExternalFundingViewModel(
        organization=external_funding.organization.name,
        project_id=external_funding.project_id,
        project_name=external_funding.project_name,
    )


@login_required
def fundingrequest_detail(request: HttpRequest, pk: int) -> HttpResponse:
    fr = FundingRequestModel.objects.get(pk=pk)
    return render(request, template_name, context(fr))


def context(fr: FundingRequestModel) -> dict[str, Any]:
    ctx = {
        "funding_request": request_viewmodel(fr),
        "submitter": submitter_viewmodel(cast(Author, fr.submitter)),
        "publication": publication_viewmodel(fr.publication),
        "label_form": ChooseLabelForm(),
    }

    if fr.external_funding:
        ctx["external_funding"] = funding_viewmodel(fr.external_funding)

    return ctx

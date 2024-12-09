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
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import Publication
from coda.fundingrequest import ReviewResult
from coda.money import Currency, Money
from coda.publication import License, Link

template_name = "fundingrequests/fundingrequest_detail.html"


class RequestViewModel(NamedTuple):
    id: int
    request_id: str
    labels: Iterable[Label]
    created_at: datetime.date
    updated_at: datetime.date
    estimated_cost: Money
    review_status: str
    review_remarks: str
    funding_amount: Money

    def is_open(self) -> bool:
        return self.review_status == ReviewResult.Open.value

    def is_approved(self) -> bool:
        return self.review_status == ReviewResult.Approved.value

    def is_rejected(self) -> bool:
        return self.review_status == ReviewResult.Rejected.value


class SubmitterViewModel(NamedTuple):
    id: int
    name: str
    affiliation: str
    roles: Iterable[str]


class PublicationViewModel(NamedTuple):
    title: str
    corresponding_author: str
    authors: Iterable[str]
    journal_title: str
    journal_eissn: str
    publisher_name: str
    publication_state: str
    publication_date: datetime.date | None
    license: str
    publication_type: str
    subject_area: str
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
        review_status=ReviewResult(fr.processing_status).value,
        review_remarks=fr.review_remarks,
        funding_amount=Money(
            fr.review_decided_funding_amount or 0,
            Currency[fr.review_decided_funding_currency or "EUR"],
        ),
    )


def submitter_viewmodel(submitter: Author) -> SubmitterViewModel:
    return SubmitterViewModel(
        id=submitter.id,
        name=submitter.name,
        affiliation=submitter.affiliation.name if submitter.affiliation else "",
        roles=[r.value for r in submitter.get_roles()],
    )


def publication_viewmodel(publication: Publication) -> PublicationViewModel:
    # FIXME: Remove type ignore. This is just a placeholder while refactoring types is in progress
    journal: Journal = publication.article_journal  # type: ignore
    return PublicationViewModel(
        title=publication.title,
        corresponding_author=cast(Author, publication.submitting_author).name,
        authors=list(publication.authors),
        journal_title=journal.title,
        journal_eissn=journal.eissn,
        publisher_name=journal.publisher.name,
        publication_state=publication.publication_state,
        publication_date=publication.online_publication_date,
        license=License[publication.license].value,
        publication_type=publication.publication_type.name,
        subject_area=publication.subject_area.name,
        oa_type=publication.open_access_type,
        references=[
            LinkDto(link_type=link.type.name, link_value=link.value).to_link()
            for link in publication.links.all()
        ],
        contracts=publication.contracts.all(),
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
        "external_funding": [funding_viewmodel(ef) for ef in fr.external_funding.all()],
    }

    return ctx

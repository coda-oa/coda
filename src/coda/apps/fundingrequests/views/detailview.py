import datetime
from collections.abc import Iterable
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from coda.apps.authors import services as author_services
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.models import ExternalFunding, Label
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import checks
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import AttachedContract
from coda.apps.publications.services import publications
from coda.domain.fundingrequest import FundingRequestId, ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import License, Link
from coda.domain.publication.payment import (
    InvoiceReceived,
    PublicationCoveredByContract,
    PublicationPaid,
    PublicationPaymentStatus,
    PublicationUnpaid,
)
from coda.domain.publication.publication import OpenAccessType, PublicationId

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

    def costs_waived(self) -> bool:
        return self.review_status == ReviewResult.Waived.value


class AuthorViewModel(NamedTuple):
    id: int
    email: str
    name: str
    affiliation: str
    role: str
    orcid: str


class PublicationViewModel(NamedTuple):
    edit_url: str
    title: str
    relevant_authors: list[AuthorViewModel]
    authors: Iterable[str]
    publishing_entity_type: str
    publishing_entity_name: str
    publishing_entity_identifier_name: str
    publishing_entity_identifier: str
    publication_state: str
    publication_date: datetime.date | None
    license: str
    publication_type: str
    subject_area: str
    oa_type: str
    references: Iterable[Link]
    contracts: Iterable[AttachedContract]
    request_remarks: str = ""
    payment_status: dict[str, Any] | None = None


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
        review_status=ReviewResult.of(fr.review.review_result).value,
        review_remarks=fr.review.remarks,
        funding_amount=Money(
            fr.review.decided_funding_amount or 0,
            Currency.from_code(fr.review.decided_funding_currency or "EUR"),
        ),
    )


def author_viewmodel(submitter_: AuthorModel) -> AuthorViewModel:
    submitter = author_services.as_domain_object(submitter_)
    return AuthorViewModel(
        id=cast(int, submitter.id),
        name=submitter.name,
        email=submitter.email,
        affiliation=submitter_.affiliation.name if submitter_.affiliation else "",
        role=submitter.role.value,
        orcid=submitter.orcid or "",
    )


def publication_viewmodel(fundingrequest: FundingRequestModel) -> PublicationViewModel:
    publication = fundingrequest.publication
    article_journal = publication.article_journal
    monograph_publisher = publication.monograph_publisher
    if article_journal is not None:
        edit_url = reverse("fundingrequests:update_publication", kwargs={"pk": fundingrequest.id})
        name = f"{article_journal.title}, {article_journal.publisher.name}"
        identifier_name = "EISSN"
        identifier = article_journal.eissn
        type = "Journal"
    elif monograph_publisher is not None:
        edit_url = reverse(
            "fundingrequests:update_monograph_meta", kwargs={"pk": fundingrequest.id}
        )
        name = monograph_publisher.name
        identifier, identifier_name = "", ""
        type = "Publisher"
    else:
        raise ValueError("Publication is neither an article nor a monograph")

    return PublicationViewModel(
        edit_url=edit_url,
        title=publication.title,
        relevant_authors=[
            author_viewmodel(author) for author in publication.relevant_authors.all()
        ],
        authors=list(publication.authors),
        publishing_entity_name=name,
        publishing_entity_type=type,
        publishing_entity_identifier_name=identifier_name,
        publishing_entity_identifier=identifier,
        publication_state=publication.publication_state,
        publication_date=publication.online_publication_date,
        license=License[publication.license].value,
        publication_type=publication.publication_type.name,
        subject_area=publication.subject_area.name,
        oa_type=OpenAccessType[publication.open_access_type].value,
        references=[
            LinkDto(link_type=link.type.name, link_value=link.value).to_link()
            for link in publication.links.all()
        ],
        contracts=[c for c in publication.attached_contracts.all()],
        request_remarks=fundingrequest.request_remarks,
        payment_status=payment_status_viewmodel(
            publications.get_payment_status(PublicationId(publication.id))
        ),
    )


def payment_status_viewmodel(payment_status: PublicationPaymentStatus) -> dict[str, Any]:
    match payment_status:
        case PublicationCoveredByContract(contract_id, contract_name, contract_year):
            return {
                "status": "Covered by contract",
                "contract_id": contract_id,
                "contract_name": contract_name,
                "contract_year": contract_year,
                "url": reverse("contracts:detail", kwargs={"pk": contract_id}),
            }

        case PublicationPaid(invoice_id, invoice_number):
            return {
                "status": "Paid",
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "url": reverse("invoices:detail", kwargs={"pk": invoice_id}),
            }

        case PublicationUnpaid():
            return {"status": "Unpaid"}
        case InvoiceReceived(invoice_id, invoice_number):
            return {
                "status": "Invoice received",
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "url": reverse("invoices:detail", kwargs={"pk": invoice_id}),
            }

    return payment_status


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
        "contact": fr.extra_contact,
        "publication": publication_viewmodel(fr),
        "label_form": ChooseLabelForm(),
        "external_funding": [funding_viewmodel(ef) for ef in fr.external_funding.all()],
        "checks": checks.get_checkrun(FundingRequestId(fr.id)),
    }

    return ctx

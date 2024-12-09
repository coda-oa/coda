from collections.abc import Iterable
from typing import cast

from django.db.models import Q

from coda.apps.authors import services as author_services
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.repositories import publication_repository
from coda.author import AuthorId
from coda.date import DateRange
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
    PaymentMethod,
    ReviewResult,
)
from coda.money import Currency, Money
from coda.publication import PublicationId
from coda.string import NonEmptyStr


def first() -> FundingRequest | None:
    model = FundingRequestModel.objects.first()
    if model:
        return as_domain_object(model)
    else:
        return None


def get_by_id(id: FundingRequestId) -> FundingRequest:
    model = FundingRequestModel.objects.get(pk=id)
    return as_domain_object(model)


def as_domain_object(model: FundingRequestModel) -> FundingRequest:
    fr = FundingRequest(
        id=FundingRequestId(model.id),
        publication=publication_repository.get_by_id(PublicationId(model.publication_id)),
        submitter=author_services.get_by_id(AuthorId(cast(int, model.submitter_id))),
        estimated_cost=Payment(
            amount=Money(model.estimated_cost, Currency.from_code(model.estimated_cost_currency)),
            method=PaymentMethod(model.payment_method),
        ),
        external_funding=[
            ExternalFunding(
                organization=FundingOrganizationId(ef.organization_id),
                project_id=NonEmptyStr(ef.project_id),
                project_name=ef.project_name,
            )
            for ef in model.external_funding.all()
        ],
    )

    match model.processing_status:
        case ReviewResult.Approved.value:
            fr.approve(
                decided_funding=Money(
                    model.review_decided_funding_amount or 0,
                    Currency.from_code(model.review_decided_funding_currency or "EUR"),
                ),
                remarks=model.review_remarks,
            )
        case ReviewResult.Rejected.value:
            fr.reject(model.review_remarks)
        case ReviewResult.Open.value:
            fr.open(model.review_remarks)

    return fr


def save_review(fr: FundingRequest) -> None:
    fr_model = FundingRequestModel.objects.get(pk=cast(FundingRequestId, fr.id))
    fr_model.processing_status = fr.review().value.lower()
    fr_model.review_decided_funding_amount = fr.funding_amount.amount
    fr_model.review_decided_funding_currency = fr.funding_amount.currency.code
    fr_model.review_remarks = fr.review_remarks
    fr_model.save()


def search(
    *,
    title: str | None = None,
    submitter: str | None = None,
    publisher: str | None = None,
    processing_states: list[str] | None = None,
    date_range: DateRange | None = None,
    labels: Iterable[int] | None = None,
) -> Iterable[FundingRequestModel]:
    query = Q()
    if title:
        query = query & Q(publication__title__icontains=title)

    if submitter:
        query = query & Q(submitter__name__icontains=submitter)

    if publisher:
        query = query & Q(publication__article_journal__publisher__name__icontains=publisher)

    if processing_states:
        query = query & Q(processing_status__in=processing_states)

    if labels:
        query = query & Q(labels__in=labels)

    if date_range:
        query = query & Q(created_at__gte=date_range.start, created_at__lte=date_range.end)

    return FundingRequestModel.objects.filter(query).distinct().order_by("-created_at")


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)

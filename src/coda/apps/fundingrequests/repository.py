from collections.abc import Iterable
from typing import Any, cast

from django.db.models import Q
from typing_extensions import TypeIs

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.repositories import publication_repository
from coda.date import DateRange
from coda.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    NoContact,
    Payment,
    PaymentMethod,
    ReviewResult,
    TPublication,
)
from coda.money import Currency, Money
from coda.publication import Monograph, OpenAccessType, Publication, PublicationId
from coda.string import NonEmptyStr


def first() -> AnyFundingRequest | None:
    model = FundingRequestModel.objects.first()
    if model:
        return as_domain_object(model)
    else:
        return None


def get_by_id(id: FundingRequestId) -> AnyFundingRequest:
    model = FundingRequestModel.objects.get(pk=id)
    return as_domain_object(model)


def get_article_request(id: FundingRequestId) -> FundingRequest[Publication]:
    fr = get_by_id(id)
    if not _is_publication_type(fr, Publication):
        raise ValueError(f"Funding request with id {id} is not an article request")

    return fr


def get_monograph_request(id: FundingRequestId) -> FundingRequest[Monograph]:
    fr = get_by_id(id)
    if not _is_publication_type(fr, Monograph):
        raise ValueError(f"Funding request with id {id} is not a monograph request")

    return fr


def _is_publication_type(
    fr: Any, publication_type: type[TPublication]
) -> TypeIs[FundingRequest[TPublication]]:
    return isinstance(fr, FundingRequest) and isinstance(fr.publication, publication_type)


def as_domain_object(model: FundingRequestModel) -> AnyFundingRequest:
    fr = FundingRequest(
        id=FundingRequestId(model.id),
        publication=publication_repository.get_by_id(PublicationId(model.publication_id)),
        extra_contact=(
            FilledContact(NonEmptyStr(model.extra_contact.name), model.extra_contact.email)
            if model.extra_contact
            else NoContact
        ),
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
        case ReviewResult.Waived.value:
            fr.waive_costs(model.review_remarks)

    return fr


def save_review(fr: AnyFundingRequest) -> None:
    fr_model = FundingRequestModel.objects.get(pk=cast(FundingRequestId, fr.id))
    fr_model.processing_status = fr.review().value.lower()
    fr_model.review_decided_funding_amount = fr.funding_amount.amount
    fr_model.review_decided_funding_currency = fr.funding_amount.currency.code
    fr_model.review_remarks = fr.review_remarks
    fr_model.save()


def search(
    *,
    title: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    processing_states: list[ReviewResult] | None = None,
    open_access_types: list[OpenAccessType] | None = None,
    date_range: DateRange | None = None,
    labels: Iterable[int] | None = None,
) -> Iterable[FundingRequestModel]:
    query = Q()
    if title:
        query = query & Q(publication__title__icontains=title)

    if author:
        query = query & Q(publication__relevant_authors__name__icontains=author)

    if publisher:
        query = query & Q(publication__article_journal__publisher__name__icontains=publisher)

    if processing_states:
        review_states = [s.value.lower() for s in processing_states]
        query = query & Q(processing_status__in=review_states)

    if open_access_types:
        oa_types = [t.value for t in open_access_types]
        query = query & Q(publication__open_access_type__in=oa_types)

    if labels:
        query = query & Q(labels__in=labels)

    if date_range:
        query = query & Q(created_at__gte=date_range.start, created_at__lte=date_range.end)

    return FundingRequestModel.objects.filter(query).distinct().order_by("-created_at")


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)

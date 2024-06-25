import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self, cast

from django.db.models import Q

from coda.apps.authors import services as author_services
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications import services as publication_services
from coda.author import AuthorId
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
    PaymentMethod,
    Review,
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
    if model.processing_status == Review.Approved.value:
        constructor = FundingRequest.approved
    elif model.processing_status == Review.Rejected.value:
        constructor = FundingRequest.rejected
    else:
        constructor = FundingRequest

    return constructor(
        id=FundingRequestId(model.id),
        publication=publication_services.get_by_id(PublicationId(model.publication_id)),
        submitter=author_services.get_by_id(AuthorId(cast(int, model.submitter_id))),
        estimated_cost=Payment(
            amount=Money(model.estimated_cost, Currency[model.estimated_cost_currency]),
            method=PaymentMethod(model.payment_method),
        ),
        external_funding=(
            ExternalFunding(
                organization=FundingOrganizationId(model.external_funding.organization_id),
                project_id=NonEmptyStr(model.external_funding.project_id),
                project_name=model.external_funding.project_name,
            )
            if model.external_funding
            else None
        ),
    )


@dataclass(frozen=True, slots=True)
class DateRange:
    start: datetime.date
    end: datetime.date

    @classmethod
    def try_fromisoformat(cls, *, start: str | None = None, end: str | None = None) -> Self:
        start_date = datetime.date.fromisoformat(start) if start else datetime.date.min
        end_date = datetime.date.fromisoformat(end) if end else datetime.date.max
        return cls(start_date, end_date)

    @classmethod
    def create(
        cls, *, start: datetime.date | None = None, end: datetime.date | None = None
    ) -> Self:
        start_date = start or datetime.date.min
        end_date = end or datetime.date.max
        return cls(start_date, end_date)


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
        query = query & Q(publication__journal__publisher__name__icontains=publisher)

    if processing_states:
        query = query & Q(processing_status__in=processing_states)

    if labels:
        query = query & Q(labels__in=labels)

    if date_range:
        query = query & Q(created_at__gte=date_range.start, created_at__lte=date_range.end)

    return FundingRequestModel.objects.filter(query).distinct().order_by("-created_at")


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)

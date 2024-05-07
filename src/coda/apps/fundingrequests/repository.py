from collections.abc import Iterable
from typing import cast

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
)
from coda.money import Currency, Money
from coda.publication import PublicationId
from coda.string import NonEmptyStr


def get_by_id(id: FundingRequestId) -> FundingRequest:
    model = FundingRequestModel.objects.get(pk=id)

    if model.processing_status == "approved":
        constructor = FundingRequest.approved
    elif model.processing_status == "rejected":
        constructor = FundingRequest.rejected
    else:
        constructor = FundingRequest

    return constructor(
        id=id,
        publication=publication_services.get_by_id(PublicationId(model.publication_id)),
        submitter=author_services.get_by_id(AuthorId(cast(int, model.submitter_id))),
        estimated_cost=Payment(
            amount=Money(model.estimated_cost, Currency[model.estimated_cost_currency]),
            method=PaymentMethod[model.payment_method.upper()],
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


def search(
    *,
    title: str | None = None,
    submitter: str | None = None,
    processing_states: list[str] | None = None,
    labels: Iterable[int] | None = None,
) -> Iterable[FundingRequestModel]:
    query = Q()
    if title:
        query = query & Q(publication__title__icontains=title)

    if submitter:
        query = query & Q(submitter__name__icontains=submitter)

    if processing_states:
        query = query & Q(processing_status__in=processing_states)

    if labels:
        query = query & Q(labels__in=labels)

    return FundingRequestModel.objects.filter(query).distinct().order_by("-created_at")


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)

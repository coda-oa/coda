from collections.abc import Iterable
from django.db import transaction

from coda.apps.authors.services import author_create
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.publications import services as publication_services
from coda.color import Color
from coda.fundingrequest import ExternalFunding, FundingRequest, FundingRequestId, Payment, Review


@transaction.atomic
def fundingrequest_create(fundingrequest: FundingRequest) -> FundingRequestId:
    author_id = author_create(fundingrequest.submitter)
    publication_id = publication_services.publication_create(fundingrequest.publication, author_id)
    request = FundingRequestModel.objects.create(
        submitter_id=author_id,
        publication_id=publication_id,
        payment_method=fundingrequest.estimated_cost.method.name.lower(),
        estimated_cost=fundingrequest.estimated_cost.amount.amount,
        estimated_cost_currency=fundingrequest.estimated_cost.amount.currency.value.code,
    )
    external_funding_create(FundingRequestId(request.id), fundingrequest.external_funding)
    return FundingRequestId(request.pk)


@transaction.atomic
def fundingrequest_funding_update(
    fundingrequest_id: FundingRequestId, payment: Payment, funding: Iterable[ExternalFunding] = ()
) -> None:
    funding_request = FundingRequestModel.objects.get(pk=fundingrequest_id)
    if funding_request.external_funding:
        funding_request.external_funding.all().delete()
        funding_request.refresh_from_db()

    external_funding = external_funding_create(fundingrequest_id, funding)
    funding_request.external_funding.set(external_funding)

    funding_request.payment_method = payment.method.name.lower()
    funding_request.estimated_cost = payment.amount.amount
    funding_request.estimated_cost_currency = payment.amount.currency.value.code
    funding_request.save()


def fundingrequest_perform_review(id: FundingRequestId, review: Review) -> None:
    funding_request = fundingrequest_repository.get_by_id(id)
    funding_request.add_review(review)
    FundingRequestModel.objects.filter(pk=id).update(
        processing_status=funding_request.review().value.lower()
    )


def external_funding_create(
    id: FundingRequestId,
    external_funding: Iterable[ExternalFunding],
) -> Iterable[ExternalFundingModel]:
    return ExternalFundingModel.objects.bulk_create(
        ExternalFundingModel(
            funding_request_id=id,
            organization_id=single_funding.organization,
            project_id=single_funding.project_id,
            project_name=single_funding.project_name,
        )
        for single_funding in external_funding
    )


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_attach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.add(funding_request)
    label.save()


def label_detach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.remove(funding_request)
    label.save()

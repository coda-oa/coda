from collections.abc import Iterable

from django.db import transaction

from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import FundingRequestContact as FundingRequestContactModel
from coda.apps.fundingrequests.models import Label
from coda.apps.publications.repositories import publication_repository
from coda.color import Color
from coda.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FundingRequestContact,
    FundingRequestId,
    Payment,
)


@transaction.atomic
def fundingrequest_create(fundingrequest: AnyFundingRequest) -> FundingRequestId:
    publication_id = publication_repository.save(fundingrequest.publication)
    request = FundingRequestModel.objects.create(
        publication_id=publication_id,
        payment_method=fundingrequest.estimated_cost.method.name.lower(),
        estimated_cost=fundingrequest.estimated_cost.amount.amount,
        estimated_cost_currency=fundingrequest.estimated_cost.amount.currency.value.code,
    )

    if fundingrequest.extra_contact:
        request.extra_contact = FundingRequestContactModel.objects.create(
            name=fundingrequest.extra_contact.name,
            email=fundingrequest.extra_contact.email,
        )

    external_funding_create(FundingRequestId(request.id), fundingrequest.external_funding)
    request.save()
    return FundingRequestId(request.pk)


@transaction.atomic
def fundingrequest_contact_update(
    fundingrequest_id: FundingRequestId, contact: FundingRequestContact
) -> None:
    model_contact, _ = FundingRequestContactModel.objects.get_or_create(
        funding_request__pk=fundingrequest_id
    )
    model_contact.name = contact.name
    model_contact.email = contact.email

    model_contact.save()


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

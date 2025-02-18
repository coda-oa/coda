from collections.abc import Iterable

from django.db import transaction

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraContactDto, PaymentDto
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.publications.dto import PublicationDto
from coda.color import Color
from coda.fundingrequest import ExternalFunding, FundingRequest, FundingRequestId


def create_fundingrequest(
    publication: PublicationDto,
    payment: PaymentDto,
    funding: Iterable[ExternalFundingDto],
    extra_contact: ExtraContactDto,
) -> FundingRequestId:
    fr = FundingRequest.new(
        publication.to_publication(),
        payment.to_payment(),
        external_funding=[f.to_external_funding() for f in funding],
        extra_contact=extra_contact.to_contact(),
    )

    return repository.save(fr)


def update_contact(fundingrequest_id: FundingRequestId, contact: ExtraContactDto) -> None:
    domain_contact = contact.to_contact()
    repository.save_contact(fundingrequest_id, domain_contact)


@transaction.atomic
def update_funding(
    fundingrequest_id: FundingRequestId,
    payment: PaymentDto,
    funding: Iterable[ExternalFundingDto] = (),
) -> None:
    repository.save_funding(
        fundingrequest_id,
        payment.to_payment(),
        map(ExternalFundingDto.to_external_funding, funding),
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

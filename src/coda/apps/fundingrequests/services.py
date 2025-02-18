import datetime
import random
from collections.abc import Iterable
from typing import Protocol

from django.db import transaction

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraContactDto, PaymentDto
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.publications.dto import PublicationBaseDto
from coda.color import Color
from coda.fundingrequest import FundingRequest, FundingRequestId
from coda.fundingrequests.identity import PublicFundingRequestId


class RequestIdGenerator(Protocol):
    def __call__(
        self, date: datetime.date | None = None, rng: random.Random | None = None
    ) -> PublicFundingRequestId:
        ...


def create_fundingrequest(
    publication: PublicationBaseDto,
    payment: PaymentDto,
    funding: Iterable[ExternalFundingDto],
    extra_contact: ExtraContactDto,
    *,
    request_id_generator: RequestIdGenerator = PublicFundingRequestId.create,
) -> FundingRequestId:
    fr = FundingRequest.new(
        publication.to_publication(),
        payment.to_payment(),
        request_id=_find_unused_request_id(request_id_generator),
        external_funding=[f.to_external_funding() for f in funding],
        extra_contact=extra_contact.to_contact(),
    )

    return repository.save(fr)


def _find_unused_request_id(request_id_generator: RequestIdGenerator) -> PublicFundingRequestId:
    request_id = request_id_generator()
    while repository.request_id_exists(request_id):
        request_id = request_id_generator()

    return request_id


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


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_attach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.add(funding_request)
    label.save()


def label_detach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.remove(funding_request)
    label.save()

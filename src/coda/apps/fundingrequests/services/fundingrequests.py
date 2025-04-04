import datetime
import itertools
import random
from collections.abc import Iterable
from typing import Protocol, overload

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraInformationDto, PaymentDto
from coda.apps.fundingrequests.services.checks import run_checks
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.apps.publications.dto import PublicationBaseDto
from coda.checks.checkfactory import CheckFactory
from coda.domain.author import Author
from coda.domain.fundingrequest import FundingRequest, FundingRequestId
from coda.domain.fundingrequest.identity import PublicFundingRequestId


class RequestIdGenerator(Protocol):
    def __call__(
        self, date: datetime.date | None = None, rng: random.Random | None = None
    ) -> PublicFundingRequestId:
        ...


def create_fundingrequest(
    publication: PublicationBaseDto,
    payment: PaymentDto,
    funding: Iterable[ExternalFundingDto],
    extra_information: ExtraInformationDto,
    *,
    request_id_generator: RequestIdGenerator = PublicFundingRequestId.create,
    checkfactory: CheckFactory | None = None,
) -> FundingRequestId:
    fr = FundingRequest.new(
        publication.to_publication(),
        payment.to_payment(),
        request_id=_find_unused_request_id(request_id_generator),
        external_funding=[f.to_external_funding() for f in funding],
        extra_contact=extra_information.extra_contact.to_contact(),
        request_remarks=extra_information.request_remarks,
    )

    fr_id = repository.save(fr)
    run_checks(fr_id, checkfactory=checkfactory)

    return fr_id


def _find_unused_request_id(request_id_generator: RequestIdGenerator) -> PublicFundingRequestId:
    request_id = request_id_generator()
    while repository.request_id_exists(request_id):
        request_id = request_id_generator()

    return request_id


def update_publication(
    fundingrequest_id: FundingRequestId,
    publication: PublicationBaseDto,
    checkfactory: CheckFactory | None = None,
) -> None:
    fr = repository.get_by_id(fundingrequest_id)
    fr.publication = publication.to_publication()
    repository.save(fr)
    run_checks(fundingrequest_id, checkfactory=checkfactory)


def update_extra_information(
    fundingrequest_id: FundingRequestId, extra_information: ExtraInformationDto
) -> None:
    fr = repository.get_by_id(fundingrequest_id)
    fr.extra_contact = extra_information.extra_contact.to_contact()
    fr.request_remarks = extra_information.request_remarks
    repository.save(fr)


def update_funding(
    fundingrequest_id: FundingRequestId,
    payment: PaymentDto,
    funding: Iterable[ExternalFundingDto] = (),
    checkfactory: CheckFactory | None = None,
) -> None:
    repository.save_funding(
        fundingrequest_id,
        payment.to_payment(),
        map(ExternalFundingDto.to_external_funding, funding),
    )
    run_checks(fundingrequest_id, checkfactory=checkfactory)


@overload
def get_institutions_allowed_as_affiliation(
    for_authors: Iterable[Author],
) -> Iterable[Institution]:
    ...


@overload
def get_institutions_allowed_as_affiliation() -> Iterable[Institution]:
    ...


def get_institutions_allowed_as_affiliation(
    for_authors: Iterable[Author] = (),
) -> Iterable[Institution]:
    allowed_institutions = tuple(institution_repository.non_virtuals())
    author_affiliations = {author.affiliation for author in for_authors if author.affiliation}
    author_affiliations = {
        affiliation
        for affiliation in author_affiliations
        if not any(affiliation == inst.pk for inst in allowed_institutions)
    }
    author_institutions = (
        institution_repository.get_by_id(affiliation) for affiliation in author_affiliations
    )
    return itertools.chain(author_institutions, allowed_institutions)

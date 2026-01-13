import datetime
import itertools
import random
from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol, overload

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import (
    CreateFundingRequestDto,
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
    UpdateReviewDto,
)
from coda.apps.fundingrequests.services.checks import run_checks
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.apps.publications.dto import PublicationBaseDto
from coda.checks.checkfactory import CheckFactory
from coda.domain import errors
from coda.domain.author import Author
from coda.domain.fundingrequest import FundingRequest, FundingRequestId
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import Review, ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import Monograph, Publication


class RequestIdGenerator(Protocol):
    def __call__(
        self, date: datetime.date | None = None, rng: random.Random | None = None
    ) -> PublicFundingRequestId: ...


def create_fundingrequest(
    creation_dto: CreateFundingRequestDto,
    *,
    request_id_generator: RequestIdGenerator = PublicFundingRequestId.create,
    checkfactory: CheckFactory | None = None,
) -> FundingRequestId:
    publication = creation_dto.publication.to_publication()

    fr = FundingRequest.new(
        publication,
        creation_dto.payment.to_payment(),
        request_id=_find_unused_request_id(request_id_generator, creation_dto.request_date),
        external_funding=[f.to_external_funding() for f in creation_dto.funding],
        extra_contact=creation_dto.extra_information.extra_contact.to_contact(),
        request_remarks=creation_dto.extra_information.request_remarks,
    )

    fr_id = repository.create(fr)
    run_checks(fr_id, checkfactory=checkfactory)

    return fr_id


@dataclass
class CreateFundingRequestFailed(errors.DomainError):
    reason: str
    legacy_id: str = ""
    publication_title: str = ""

    @property
    def request_key(self) -> str:
        if self.legacy_id:
            return self.legacy_id

        return self.publication_title


def try_into_funding_request(
    request_id: PublicFundingRequestId, creation_dto: CreateFundingRequestDto
) -> AnyFundingRequest:
    try:
        return FundingRequest.new(
            creation_dto.publication.to_publication(),
            creation_dto.payment.to_payment(),
            request_id=request_id,
            external_funding=[f.to_external_funding() for f in creation_dto.funding],
            extra_contact=creation_dto.extra_information.extra_contact.to_contact(),
            request_remarks=creation_dto.extra_information.request_remarks,
            legacy_request_id=creation_dto.legacy_request_id,
        )
    except ValueError as e:
        raise CreateFundingRequestFailed(
            reason=str(e),
            legacy_id=creation_dto.legacy_request_id,
            publication_title=creation_dto.publication.meta.title,
        )


def bulk_create_fundingrequests(
    creation_dtos: Iterable[CreateFundingRequestDto],
    *,
    request_id_generator: RequestIdGenerator = PublicFundingRequestId.create,
    checkfactory: CheckFactory | None = None,
) -> tuple[Iterable[FundingRequestId], list[CreateFundingRequestFailed]]:
    _ = checkfactory
    ids = [
        _find_unused_request_id(request_id_generator, creation_dto.request_date)
        for creation_dto in creation_dtos
    ]

    with errors.capture(CreateFundingRequestFailed) as capture:
        parsed = errors.results(
            capture(try_into_funding_request, request_id, creation_dto)
            for request_id, creation_dto in zip(ids, creation_dtos)
        )

    funding_requests, errors_ = parsed.split()
    return repository.create_many(funding_requests), errors_


def _find_unused_request_id(
    request_id_generator: RequestIdGenerator, request_date: datetime.date | None = None
) -> PublicFundingRequestId:
    request_id = request_id_generator(date=request_date)
    while repository.request_id_exists(request_id):
        request_id = request_id_generator()

    return request_id


def update_publication(
    fundingrequest_id: FundingRequestId,
    publication: PublicationBaseDto,
    checkfactory: CheckFactory | None = None,
) -> None:
    fr = repository.get_by_id(fundingrequest_id)
    fr.publication = publication.to_publication(fr.publication.id)
    repository.update(fr)
    run_checks(fundingrequest_id, checkfactory=checkfactory)


def update_publication_preserving_contracts(
    fundingrequest_id: FundingRequestId,
    publication: PublicationBaseDto,
    checkfactory: CheckFactory | None = None,
) -> None:
    """
    Update publication metadata while preserving existing contract years.

    Used when updating publication details without modifying contracts.
    This avoids validation errors for contract years that may have become
    invalid due to contract period changes.

    The existing contract years are preserved from the database, allowing
    partial updates to publication metadata (title, authors, etc.) without
    requiring users to fix invalid contract years that are unrelated to
    their current task.

    Also preserves journal (for articles) or publisher (for monographs) since
    these are edited on the contract step, not the publication metadata step.
    """
    fr = repository.get_by_id(fundingrequest_id)
    existing_contracts = fr.publication.contracts

    # Replace contracts in DTO with empty list to avoid validation during conversion
    # We'll restore the actual contracts after conversion
    publication.contracts = []

    # Convert DTO to publication with updated metadata but empty contracts
    updated_publication = publication.to_publication(fr.publication.id)

    # Preserve contracts, journal (articles), and publisher (monographs) from database
    # These are edited in the contract step, not the publication metadata step
    replacements: dict[str, Any] = {"contracts": existing_contracts}

    # Preserve journal for articles or publisher for monographs
    if isinstance(fr.publication, Publication):
        replacements["journal"] = fr.publication.journal
    elif isinstance(fr.publication, Monograph):
        replacements["publisher"] = fr.publication.publisher

    fr.publication = replace(updated_publication, **replacements)

    repository.update(fr)
    run_checks(fundingrequest_id, checkfactory=checkfactory)


def update_extra_information(
    fundingrequest_id: FundingRequestId, extra_information: ExtraInformationDto
) -> None:
    fr = repository.get_by_id(fundingrequest_id)
    fr.extra_contact = extra_information.extra_contact.to_contact()
    fr.request_remarks = extra_information.request_remarks
    repository.update(fr)


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


def update_review(fundingrequest_id: FundingRequestId, review: UpdateReviewDto) -> None:
    if not review.result:
        review = _keep_result(fundingrequest_id, review)

    review_ = Review(
        fundingrequest_id,
        Money(
            Decimal(review.decided_funding_amount),
            Currency.from_code(review.decided_funding_currency),
        ),
        remarks=review.reviewer_remarks,
        result=ReviewResult.of(review.result),
    )
    repository.save_review(review_)


def _keep_result(fundingrequest_id: FundingRequestId, review: UpdateReviewDto) -> UpdateReviewDto:
    old_review = repository.get_review(fundingrequest_id)
    review = review.model_copy()
    review.result = old_review.result.value
    return review


@overload
def get_institutions_allowed_as_affiliation(
    for_authors: Iterable[Author],
) -> Iterable[Institution]: ...


@overload
def get_institutions_allowed_as_affiliation() -> Iterable[Institution]: ...


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

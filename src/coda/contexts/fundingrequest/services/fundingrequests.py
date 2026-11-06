import datetime
import itertools
import logging
import random
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Protocol, cast, overload

from coda.apps.fundingrequests import repository
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.apps.invoices import funding_source_repository
from coda.apps.publications.dto import ContractYearDto, parse_publication_state
from coda.checks.checkfactory import CheckFactory
from coda.contexts.finance.services import budget_service
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    CreateReviewDto,
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
    UpdatePublicationMetadataCommand,
    UpdateReviewDto,
)
from coda.contexts.fundingrequest.services.allowed_vocabularies import (
    AllowedConcepts,
)
from coda.contexts.fundingrequest.services.checks import run_checks
from coda.domain import errors
from coda.domain.author import Author, AuthorNames
from coda.domain.contract import GetContractById, PublisherId
from coda.domain.errors import DomainError
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest import FundingRequest, FundingRequestId
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import (
    DecidedFunding,
    FundingSplits,
    Review,
    ReviewResult,
    ReviewSplit,
)
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors, JournalId, License, OpenAccessType
from coda.domain.publication.publication import Monograph, Publication
from coda.domain.string import NonEmptyStr


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
    AllowedConcepts.for_new_publication(publication.kind).validate(
        publication.publication_type,
        publication.subject_area,
    )
    # For single creation, fetch existing IDs to ensure uniqueness
    existing_ids = set(repository.get_all_request_ids())

    fr = FundingRequest.new(
        publication,
        creation_dto.payment.to_payment(),
        request_id=_find_unused_request_id(
            request_id_generator, existing_ids, creation_dto.request_date
        ),
        external_funding=[f.to_external_funding() for f in creation_dto.funding],
        extra_contact=creation_dto.extra_information.extra_contact.to_contact(),
        request_remarks=creation_dto.extra_information.request_remarks,
    )

    fr_id = repository.create(cast(AnyFundingRequest, fr))
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


def _create_review_from_dto(review_dto: CreateReviewDto | None) -> Review | None:
    """Convert CreateReviewDto to domain Review object.

    Args:
        review_dto: Optional review DTO from creation command

    Returns:
        Domain Review object, or None if no review data provided
    """
    if not review_dto:
        return None

    return Review(
        fundingrequest=None,
        decided_funding=Money(
            str(review_dto.decided_funding_amount),
            Currency.from_code(review_dto.decided_funding_currency),
        ),
        result=ReviewResult.of(review_dto.result),
        remarks=review_dto.reviewer_remarks,
    )


def try_into_funding_request(
    request_id: PublicFundingRequestId,
    creation_dto: CreateFundingRequestDto,
    get_contract_by_id: GetContractById | None = None,
) -> AnyFundingRequest:
    """Convert creation DTO to domain FundingRequest object.

    Args:
        request_id: Generated public funding request ID
        creation_dto: DTO containing funding request data
        get_contract_by_id: Optional callable to fetch Contract by ID.
            Passed through to publication DTO conversion.

    Returns:
        Domain FundingRequest object

    Raises:
        CreateFundingRequestFailed: If validation fails during conversion
    """
    try:
        return cast(
            AnyFundingRequest,
            FundingRequest(
                id=None,
                request_id=request_id,
                publication=creation_dto.publication.to_publication(
                    get_contract_by_id=get_contract_by_id
                ),
                estimated_cost=creation_dto.payment.to_payment(),
                external_funding=[f.to_external_funding() for f in creation_dto.funding],
                extra_contact=creation_dto.extra_information.extra_contact.to_contact(),
                request_remarks=creation_dto.extra_information.request_remarks,
                legacy_request_id=creation_dto.legacy_request_id,
                review=_create_review_from_dto(creation_dto.review),
            ),
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
    get_contract_by_id: GetContractById | None = None,
) -> tuple[Iterable[FundingRequestId], list[CreateFundingRequestFailed]]:
    """Bulk create funding requests from DTOs.

    Args:
        creation_dtos: Iterable of creation DTOs
        request_id_generator: Callable to generate unique request IDs
        checkfactory: Optional check factory for validation
        get_contract_by_id: Optional callable to fetch Contract by ID.
            If provided, used instead of database queries for contract retrieval.

    Returns:
        Tuple of (created FundingRequest IDs, list of failed creation attempts)
    """
    _ = checkfactory

    # Fetch all existing request IDs once for efficient in-memory checking
    existing_ids = set(repository.get_all_request_ids())

    ids = [
        _find_unused_request_id(request_id_generator, existing_ids, creation_dto.request_date)
        for creation_dto in creation_dtos
    ]

    with errors.capture(CreateFundingRequestFailed) as capture:
        parsed = errors.results(
            capture(try_into_funding_request, request_id, creation_dto, get_contract_by_id)
            for request_id, creation_dto in zip(ids, creation_dtos)
        )

    funding_requests, errors_ = parsed.split()
    return repository.create_many(funding_requests), errors_


def _find_unused_request_id(
    request_id_generator: RequestIdGenerator,
    existing_ids: set[str],
    request_date: datetime.date | None = None,
) -> PublicFundingRequestId:
    """Find an unused request ID by checking against a set of existing IDs.

    Args:
        request_id_generator: Function to generate new request IDs
        existing_ids: Set of existing request IDs to check against (modified in-place)
        request_date: Optional date to use for ID generation

    Returns:
        A unique PublicFundingRequestId that doesn't exist in existing_ids
    """
    request_id = request_id_generator(date=request_date)
    while str(request_id) in existing_ids:
        request_id = request_id_generator()

    # Add the new ID to the set to prevent duplicates within the same batch
    existing_ids.add(str(request_id))
    return request_id


def update_publication_metadata(
    fundingrequest_id: FundingRequestId,
    command: UpdatePublicationMetadataCommand,
    checkfactory: CheckFactory | None = None,
) -> None:
    """Updates only publication metadata (title, authors, dates, license, etc.)

    Preserves existing contracts, journal/publisher unchanged.
    Used when early-completing from PublicationStep without visiting contract steps.

    Args:
        fundingrequest_id: ID of the funding request to update
        command: Publication metadata command from the application layer
        checkfactory: Optional check factory for running validation checks
    """
    fr = repository.get_by_id(fundingrequest_id)
    publication = fr.publication

    logger = logging.getLogger(__name__)
    meta = command.meta

    logger.info(repr(meta))
    incoming_publication_type = meta.publication_type.to_concept()
    incoming_subject_area = meta.subject_area.to_concept()

    AllowedConcepts.for_existing_publication(publication).validate(
        incoming_publication_type,
        incoming_subject_area,
    )

    publication.title = NonEmptyStr(meta.title)
    publication.publication_type = incoming_publication_type
    publication.subject_area = incoming_subject_area
    publication.open_access_type = OpenAccessType[meta.open_access_type]
    publication.license = License.of(meta.license)
    publication.publication_state = parse_publication_state(meta)

    relevant_authors = Authors(a.to_author() for a in command.relevant_authors)
    other_authors = AuthorNames(command.other_authors)
    publication.relevant_authors = relevant_authors
    publication.other_authors = other_authors

    publication.links = {link.to_link() for link in command.links}

    repository.update(fr)
    run_checks(fundingrequest_id, checkfactory=checkfactory)


def update_publication_journal_and_contracts(
    fundingrequest_id: FundingRequestId,
    journal: JournalId,
    contract_dtos: list[ContractYearDto],
    checkfactory: CheckFactory | None = None,
) -> None:
    """Updates journal and contracts for article publications.

    Validates contract years before updating. Raises InvalidContractYearError
    if any contract year is invalid for its contract's period.

    Args:
        fundingrequest_id: ID of the funding request to update
        journal: Journal ID for the article
        contract_dtos: List of contract year DTOs
        checkfactory: Optional check factory for running validation checks
    """
    fr = repository.get_by_id(fundingrequest_id)

    contracts = tuple(dto.to_contract_year() for dto in contract_dtos)

    assert isinstance(fr.publication, Publication)
    fr.publication.journal = journal
    fr.publication.contracts = contracts

    repository.update(fr)
    run_checks(fundingrequest_id, checkfactory=checkfactory)


def update_publication_publisher_and_contracts(
    fundingrequest_id: FundingRequestId,
    publisher: PublisherId,
    contract_dtos: list[ContractYearDto],
    checkfactory: CheckFactory | None = None,
) -> None:
    """Updates publisher and contracts for monograph publications.

    Validates contract years before updating. Raises InvalidContractYearError
    if any contract year is invalid for its contract's period.

    Args:
        fundingrequest_id: ID of the funding request to update
        publisher: Publisher ID for the monograph
        contract_dtos: List of contract year DTOs
        checkfactory: Optional check factory for running validation checks
    """
    fr = repository.get_by_id(fundingrequest_id)

    contracts = tuple(dto.to_contract_year() for dto in contract_dtos)

    assert isinstance(fr.publication, Monograph)
    fr.publication.publisher = publisher
    fr.publication.contracts = contracts

    repository.update(fr)
    run_checks(fundingrequest_id, checkfactory=checkfactory)


def update_extra_information(
    fundingrequest_id: FundingRequestId, extra_information: ExtraInformationDto
) -> None:
    fr = repository.get_by_id(fundingrequest_id)
    fr.extra_contact = extra_information.extra_contact.to_contact()
    fr.request_remarks = extra_information.request_remarks
    repository.update(fr)
    if extra_information.reviewer_remarks is not None:
        review = repository.get_review(fundingrequest_id)
        repository.save_review(replace(review, remarks=extra_information.reviewer_remarks))


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
    """Saves a review decision and books its budget commitments.

    An approved review validates its splits and capacity-checks only the
    positive delta over the review's own persisted splits. Unchanged
    re-approvals book nothing. A missing result keeps the persisted one.

    The capacity decision is made from a pre-read snapshot: two concurrent
    saves against the same budget (or a transfer landing in between) can both
    pass. Transfers serialize via row locks; review saves do not."""
    if not review.result:
        review = _keep_result(fundingrequest_id, review)

    result = ReviewResult.of(review.result)
    funding = _funding(review)
    _validate(funding, fundingrequest_id)
    review_ = Review(
        fundingrequest_id,
        funding.total,
        remarks=review.reviewer_remarks,
        result=result,
        funding_splits=funding.splits if result == ReviewResult.Approved else FundingSplits(()),
    )
    for row in repository.save_review(review_):
        budget_service.record_commitment(
            FundingSourceId(row.funding_source_id),
            Money(row.amount, funding.total.currency),
            review_split=row.pk,
        )


def _funding(review: UpdateReviewDto) -> "DecidedFunding":
    decided_funding = Money(
        review.decided_funding_amount,
        Currency.from_code(review.decided_funding_currency),
    )
    splits = FundingSplits.of(
        ReviewSplit(
            FundingSourceId(split.funding_source_id),
            Money(split.amount, decided_funding.currency),
        )
        for split in review.funding_splits
    )
    return DecidedFunding(decided_funding, splits)


def _validate(
    funding: "DecidedFunding",
    fundingrequest_id: FundingRequestId,
) -> None:
    _validate_splits(funding)
    persisted_review = repository.get_review(fundingrequest_id)
    _ensure_same_currency(
        persisted_review.funding_splits, persisted_review.decided_funding.currency, funding
    )
    for source, delta in funding.delta_over(persisted_review.funding_splits).items():
        budget_service.ensure_capacity(source, delta)


def _validate_splits(funding: DecidedFunding) -> None:
    """Validates the funding splits against the decided funding.

    The splits must sum to the decided amount. Splits are stored without a
    currency and count as-is in the budget's currency: a split decided in a
    foreign currency would silently bypass the capacity guard (a foreign
    commitment is rate-pending and invisible to it) and mis-state balances
    on read. Decisions have a known currency, so each budget's currency must
    match the decided currency."""
    if not funding.all_assigned():
        raise InvalidFundingSplit(
            f"funding splits sum to {funding.split_sum()} but the decided funding is {funding.total}"
        )
    for source_id in funding.splits.sources():
        source = funding_source_repository.get_by_id(source_id)
        if not isinstance(source, Budget):
            raise InvalidFundingSplit(
                f"funding split references a non-budget funding source: {source.name}"
            )
        if source.amount.currency != funding.total.currency:
            raise InvalidFundingSplit(
                _split_currency_mismatch_message(
                    funding.total.currency, source.name, source.amount.currency
                )
            )


def _ensure_same_currency(
    persisted_splits: FundingSplits, persisted_currency: Currency, funding: DecidedFunding
) -> None:
    """
    The splits belong to the review and are denominated in the review's
    decided currency. If that currency changed, the persisted splits belong
    to the old decision: refuse to re-interpret them in the new currency
    where the capacity delta would consume them.
    """
    same_currency = persisted_currency == funding.total.currency
    if not persisted_splits.splits or same_currency:
        return

    sources_overlap = funding.splits.sources() & persisted_splits.sources()
    if sources_overlap:
        raise InvalidFundingSplit(
            f"the decided currency changed from "
            f"{persisted_currency.code} to "
            f"{funding.total.currency.code}: the persisted funding splits "
            f"belong to the old decision — re-enter the funding splits"
        )


def _split_currency_mismatch_message(
    decided: Currency, budget_name: str, budget_currency: Currency
) -> str:
    return (
        f"funding split for budget '{budget_name}' is decided in "
        f"{decided.code}, but the budget is denominated in {budget_currency.code}"
    )


class InvalidFundingSplit(DomainError):
    pass


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
    author_institutions = list(institution_repository.get_many_by_id(author_affiliations))
    return itertools.chain(author_institutions, allowed_institutions)

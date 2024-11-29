from dataclasses import dataclass, field
import enum
from collections.abc import Iterable
from typing import NamedTuple, NewType

from coda.author import Author
from coda.money import Money
from coda.money._currency import Currency
from coda.publication import Publication
from coda.string import NonEmptyStr

FundingRequestId = NewType("FundingRequestId", int)
FundingOrganizationId = NewType("FundingOrganizationId", int)


class ReviewResult(enum.Enum):
    Open = "open"
    Approved = "approved"
    Rejected = "rejected"
    Withdrawn = "withdrawn"


@dataclass(frozen=True)
class Review:
    decided_funding: Money = field(default_factory=lambda: Money(0, Currency.EUR))
    result: ReviewResult = ReviewResult.Open
    remarks: str = ""


class ExternalFunding(NamedTuple):
    organization: FundingOrganizationId
    project_id: NonEmptyStr
    project_name: str


class PaymentMethod(enum.Enum):
    Direct = "direct"
    Reimbursement = "reimbursement"
    Unknown = "unknown"


class Payment(NamedTuple):
    amount: Money
    method: PaymentMethod


class FundingRequestLocked(RuntimeError):
    pass


class FundingRequest:
    def __init__(
        self,
        id: FundingRequestId | None,
        publication: Publication,
        submitter: Author,
        estimated_cost: Payment,
        external_funding: Iterable[ExternalFunding] = (),
    ) -> None:
        self.id = id
        self._publication = publication
        self._submitter = submitter
        self.estimated_cost = estimated_cost
        self.external_funding = tuple(external_funding)
        self._review = Review()

    @classmethod
    def new(
        cls,
        publication: Publication,
        submitter: Author,
        estimated_cost: Payment,
        external_funding: Iterable[ExternalFunding] = (),
    ) -> "FundingRequest":
        return cls(None, publication, submitter, estimated_cost, external_funding)

    @classmethod
    def approved(
        cls,
        id: FundingRequestId,
        publication: Publication,
        submitter: Author,
        estimated_cost: Payment,
        external_funding: Iterable[ExternalFunding] = (),
    ) -> "FundingRequest":
        request = cls(id, publication, submitter, estimated_cost, external_funding)
        request._review = Review(result=ReviewResult.Approved)
        return request

    @classmethod
    def rejected(
        cls,
        id: FundingRequestId,
        publication: Publication,
        submitter: Author,
        estimated_cost: Payment,
        external_funding: Iterable[ExternalFunding] = (),
    ) -> "FundingRequest":
        request = cls(id, publication, submitter, estimated_cost, external_funding)
        request._review = Review(result=ReviewResult.Rejected)
        return request

    def approve(self, decided_funding: Money, remarks: str = "") -> None:
        self._review = Review(decided_funding, ReviewResult.Approved, remarks)

    def reject(self, remarks: str = "") -> None:
        self._review = Review(result=ReviewResult.Rejected, remarks=remarks)

    def open(self) -> None:
        self._review = Review(
            decided_funding=self._review.decided_funding, remarks=self._review.remarks
        )

    def is_open(self) -> bool:
        return self._review.result == ReviewResult.Open

    def is_approved(self) -> bool:
        return self._review.result == ReviewResult.Approved

    def is_rejected(self) -> bool:
        return self._review.result == ReviewResult.Rejected

    @property
    def submitter(self) -> Author:
        return self._submitter

    @submitter.setter
    def submitter(self, author: Author) -> None:
        if not self.is_open():
            raise FundingRequestLocked("Cannot change submitter of an approved request")

        self._submitter = author

    @property
    def publication(self) -> Publication:
        return self._publication

    @publication.setter
    def publication(self, publication: Publication) -> None:
        if not self.is_open():
            raise FundingRequestLocked("Cannot change publication of an approved request")

        self._publication = publication

    def review(self) -> ReviewResult:
        return self._review.result

    @property
    def funding_amount(self) -> Money:
        return self._review.decided_funding

    @property
    def review_remarks(self) -> str:
        return self._review.remarks

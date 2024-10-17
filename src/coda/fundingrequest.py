import enum
from collections.abc import Iterable
from typing import NamedTuple, NewType

from coda.author import Author
from coda.money import Money
from coda.publication import Publication
from coda.string import NonEmptyStr

FundingRequestId = NewType("FundingRequestId", int)
FundingOrganizationId = NewType("FundingOrganizationId", int)


class Review(enum.Enum):
    Open = "open"
    Approved = "approved"
    Rejected = "rejected"
    Withdrawn = "withdrawn"


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
        self.external_funding = external_funding
        self._review = Review.Open

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
        request._review = Review.Approved
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
        request._review = Review.Rejected
        return request

    def add_review(self, review: Review) -> None:
        self._review = review

    def open(self) -> None:
        self._review = Review.Open

    def is_open(self) -> bool:
        return self._review == Review.Open

    def is_approved(self) -> bool:
        return self._review == Review.Approved

    def is_rejected(self) -> bool:
        return self._review == Review.Rejected

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

    def review(self) -> Review:
        return self._review

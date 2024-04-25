import enum
from typing import NamedTuple, NewType

from coda.author import Author
from coda.money import Money
from coda.publication import Publication
from coda.string import NonEmptyStr

FundingRequestId = NewType("FundingRequestId", int)
FundingOrganizationId = NewType("FundingOrganizationId", int)


class OpenAccessType(enum.Enum):
    Gold = enum.auto()
    Diamond = enum.auto()
    Hybrid = enum.auto()
    Unknown = enum.auto()
    Closed = enum.auto()


class ProcessingStatus(enum.Enum):
    Open = enum.auto()
    Approved = enum.auto()
    Rejected = enum.auto()
    Withdrawn = enum.auto()


class Review(NamedTuple):
    open_access_type: OpenAccessType = OpenAccessType.Unknown
    status: ProcessingStatus = ProcessingStatus.Open

    @classmethod
    def approve(cls, open_access_type: OpenAccessType = OpenAccessType.Unknown) -> "Review":
        return cls(open_access_type=open_access_type, status=ProcessingStatus.Approved)

    @classmethod
    def reject(cls, open_access_type: OpenAccessType = OpenAccessType.Unknown) -> "Review":
        return cls(open_access_type=open_access_type, status=ProcessingStatus.Rejected)


class ExternalFunding(NamedTuple):
    organization: FundingOrganizationId
    project_id: NonEmptyStr
    project_name: str


class FundingRequestLocked(RuntimeError):
    pass


class FundingRequest:
    def __init__(
        self,
        id: FundingRequestId,
        publication: Publication,
        submitter: Author,
        estimated_cost: Money,
        external_funding: "ExternalFunding",
    ) -> None:
        self.id = id
        self._publication = publication
        self._submitter = submitter
        self.estimated_cost = estimated_cost
        self.external_funding = external_funding
        self._review: Review = Review()

    def add_review(self, review: Review) -> None:
        if self._review.status != ProcessingStatus.Open:
            raise FundingRequestLocked("Cannot change review of a closed request")

        self._review = review

    def open(self) -> None:
        self._review = Review(self._review.open_access_type, ProcessingStatus.Open)

    def is_open(self) -> bool:
        return self._review.status == ProcessingStatus.Open

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

    def review(self) -> Review | None:
        return self._review

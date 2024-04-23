import enum
from typing import Any, NamedTuple, NewType

from coda.author import AuthorId, AuthorList
from coda.money import Money
from coda.publication import JournalId, Publication, PublicationId
from coda.string import NonEmptyStr

FundingRequestId = NewType("FundingRequestId", int)
FundingOrganizationId = NewType("FundingOrganizationId", int)


class ProcessingStatus(enum.Enum):
    Open = enum.auto()
    Approved = enum.auto()
    Rejected = enum.auto()
    Withdrawn = enum.auto()


class ExternalFunding(NamedTuple):
    organization: FundingOrganizationId
    project_id: NonEmptyStr
    project_name: str


class FundingRequestLocked(RuntimeError):
    pass


class LockedPublication(Publication):
    def __init__(
        self, id: PublicationId, title: str, journal: JournalId, authors: AuthorList | None = None
    ) -> None:
        super().__init__(id, title, journal, authors)
        self._initialized = True

    @classmethod
    def lock(cls, publication: Publication) -> "LockedPublication":
        return cls(
            id=publication.id,
            title=publication.title,
            journal=publication.journal,
            authors=publication.authors,
        )

    def unlock(self) -> Publication:
        return Publication(
            id=self.id,
            title=self.title,
            journal=self.journal,
            authors=self.authors,
        )

    def __setattr__(self, name: str, value: Any) -> None:
        if not hasattr(self, "_initialized"):
            super().__setattr__(name, value)
        else:
            raise FundingRequestLocked("Cannot change publication journal")


class FundingRequest:
    def __init__(
        self,
        id: FundingRequestId,
        publication: Publication,
        submitter: AuthorId,
        estimated_cost: Money,
        external_funding: "ExternalFunding",
    ) -> None:
        self._id = id
        self._publication = publication
        self._submitter = submitter
        self._estimated_cost = estimated_cost
        self._external_funding = external_funding
        self._status = ProcessingStatus.Open

    def _lock(self) -> None:
        self._publication = LockedPublication.lock(self._publication)

    def _unlock(self) -> None:
        if isinstance(self._publication, LockedPublication):
            self._publication = self._publication.unlock()

    def approve(self) -> ProcessingStatus:
        if self._status == ProcessingStatus.Rejected:
            raise ValueError("Cannot approve a rejected request")

        self._lock()
        self._status = ProcessingStatus.Approved
        return self._status

    def reject(self) -> ProcessingStatus:
        if self._status == ProcessingStatus.Approved:
            raise ValueError("Cannot reject an approved request")

        self._lock()
        self._status = ProcessingStatus.Rejected
        return self._status

    def open(self) -> ProcessingStatus:
        self._status = ProcessingStatus.Open
        self._unlock()
        return self._status

    def status(self) -> ProcessingStatus:
        return self._status

    def is_open(self) -> bool:
        return self._status == ProcessingStatus.Open

    @property
    def publication(self) -> Publication:
        return self._publication

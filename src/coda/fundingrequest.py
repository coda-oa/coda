import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final, Generic, NamedTuple, NewType, TypeAlias, TypeVar

from coda.fundingrequests.identity import PublicFundingRequestId
from coda.money import Money
from coda.money._currency import Currency
from coda.publication import BasePublication, Monograph, Publication
from coda.string import NonEmptyStr

FundingRequestId = NewType("FundingRequestId", int)
FundingOrganizationId = NewType("FundingOrganizationId", int)


class ReviewResult(enum.Enum):
    Open = "open"
    Waived = "waived"
    Approved = "approved"
    Rejected = "rejected"
    Closed = "closed"


@dataclass(frozen=True)
class Review:
    decided_funding: Money = field(default_factory=lambda: Money(0, Currency.EUR))
    result: ReviewResult = ReviewResult.Open
    remarks: str = ""

    def with_remarks(self, remarks: str) -> "Review":
        return Review(self.decided_funding, self.result, remarks)


class ExternalFunding(NamedTuple):
    organization: FundingOrganizationId
    project_id: NonEmptyStr
    project_name: str


class PaymentMethod(enum.Enum):
    Direct = "direct"
    Reimbursement = "reimbursement"
    Unknown = "unknown"


@dataclass
class Payment:
    amount: Money
    method: PaymentMethod

    def __post_init__(self) -> None:
        self._waived = False


TPublication = TypeVar("TPublication", bound=BasePublication)


@dataclass
class FilledContact:
    name: NonEmptyStr
    email: str


@dataclass(frozen=True, slots=True)
class _NoContact:
    name: str = ""
    email: str = ""

    def __bool__(self) -> bool:
        return False


NoContact: Final = _NoContact()
FundingRequestContact = FilledContact | _NoContact


class FundingRequest(Generic[TPublication]):
    def __init__(
        self,
        id: FundingRequestId | None,
        request_id: PublicFundingRequestId,
        publication: TPublication,
        estimated_cost: Payment,
        external_funding: Iterable[ExternalFunding] = (),
        extra_contact: FundingRequestContact = NoContact,
        request_remarks: str = "",
    ) -> None:
        self.id = id
        self.request_id = request_id
        self.publication = publication
        self.extra_contact = extra_contact
        self.estimated_cost = estimated_cost
        self.external_funding = tuple(external_funding)
        self._review = Review()
        self.request_remarks = request_remarks

    @classmethod
    def new(
        cls,
        publication: TPublication,
        estimated_cost: Payment,
        request_id: PublicFundingRequestId | None = None,
        external_funding: Iterable[ExternalFunding] = (),
        extra_contact: FundingRequestContact | _NoContact = NoContact,
        request_remarks: str = "",
    ) -> "FundingRequest[TPublication]":
        return cls(
            None,
            request_id or PublicFundingRequestId.create(),
            publication,
            estimated_cost,
            external_funding,
            extra_contact,
            request_remarks,
        )

    @property
    def request_date(self) -> datetime.date:
        return self.request_id.date()

    def approve(self, decided_funding: Money, remarks: str = "") -> None:
        self._review = Review(decided_funding, ReviewResult.Approved, remarks)

    def reject(self, remarks: str = "") -> None:
        self._review = Review(result=ReviewResult.Rejected, remarks=remarks)

    def open(self, remarks: str = "") -> None:
        self._review = Review(
            decided_funding=self._review.decided_funding,
            remarks=remarks,
        )

    def waive_costs(self, remarks: str = "") -> None:
        self._review = Review(
            result=ReviewResult.Waived,
            decided_funding=Money(0, Currency.EUR),
            remarks=remarks,
        )

    def close(self, remarks: str = "") -> None:
        self._review = Review(result=ReviewResult.Closed, remarks=remarks)

    def update_remarks(self, remarks: str) -> None:
        self._review = self._review.with_remarks(remarks)

    def is_open(self) -> bool:
        return self._review.result == ReviewResult.Open

    def is_approved(self) -> bool:
        return self._review.result == ReviewResult.Approved

    def is_rejected(self) -> bool:
        return self._review.result == ReviewResult.Rejected

    def costs_waived(self) -> bool:
        return self._review.result == ReviewResult.Waived

    def review(self) -> ReviewResult:
        return self._review.result

    @property
    def funding_amount(self) -> Money:
        return self._review.decided_funding

    @property
    def review_remarks(self) -> str:
        return self._review.remarks


AnyFundingRequest: TypeAlias = (
    FundingRequest[BasePublication] | FundingRequest[Publication] | FundingRequest[Monograph]
)

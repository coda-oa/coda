import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Generic, NamedTuple, TypeAlias, TypeVar

from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import Review, ReviewResult
from coda.domain.money import Money
from coda.domain.publication import BasePublication, Monograph, Publication
from coda.domain.string import NonEmptyStr
from coda.entityid import EntityId

# FundingRequestId = NewType("FundingRequestId", int)
# FundingOrganizationId = NewType("FundingOrganizationId", int)


class FundingRequestId(EntityId): ...


class FundingOrganizationId(EntityId): ...


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
    external_costsplitting: bool | None = None

    def __post_init__(self) -> None:
        self._waived = False


TPublication = TypeVar("TPublication", bound=BasePublication)
TCheckPublication = TypeVar("TCheckPublication", bound=BasePublication)


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
        id: FundingRequestId,
        request_id: PublicFundingRequestId,
        publication: TPublication,
        estimated_cost: Payment,
        legacy_request_id: str = "",
        external_funding: Iterable[ExternalFunding] = (),
        extra_contact: FundingRequestContact = NoContact,
        request_remarks: str = "",
        review: Review | None = None,
    ) -> None:
        self.id = id
        self.legacy_request_id = legacy_request_id
        self.request_id = request_id
        self.publication = publication
        self.extra_contact = extra_contact
        self.estimated_cost = estimated_cost
        self.external_funding = tuple(external_funding)
        self.request_remarks = request_remarks
        self._review = review or Review()

    @classmethod
    def new(
        cls,
        publication: TPublication,
        estimated_cost: Payment,
        request_id: PublicFundingRequestId | None = None,
        external_funding: Iterable[ExternalFunding] = (),
        extra_contact: FundingRequestContact | _NoContact = NoContact,
        request_remarks: str = "",
        legacy_request_id: str = "",
    ) -> "FundingRequest[TPublication]":
        return cls(
            FundingRequestId(),
            request_id=request_id or PublicFundingRequestId.create(),
            publication=publication,
            estimated_cost=estimated_cost,
            external_funding=external_funding,
            extra_contact=extra_contact,
            request_remarks=request_remarks,
            legacy_request_id=legacy_request_id,
        )

    def set_review(self, result: ReviewResult, decided_funding: Money, remarks: str) -> None:
        self._review = Review(decided_funding, result, remarks)

    @property
    def request_date(self) -> datetime.date:
        return self.request_id.date()

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

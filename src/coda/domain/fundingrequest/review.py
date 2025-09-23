import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coda.domain.money import Currency, Money

if TYPE_CHECKING:
    from coda.domain.fundingrequest import FundingRequestId


class ReviewResult(enum.Enum):
    Open = "open"
    Waived = "waived"
    Approved = "approved"
    Rejected = "rejected"
    Closed = "closed"

    @classmethod
    def of(cls, value: str) -> "ReviewResult":
        return cls(value.strip().lower())


@dataclass(frozen=True)
class Review:
    fundingrequest: "FundingRequestId | None" = None
    decided_funding: Money = field(default_factory=lambda: Money(0, Currency.EUR))
    result: ReviewResult = ReviewResult.Open
    remarks: str = ""

    def approved(self, decided_funding: Money, remarks: str = "") -> "Review":
        return Review(self.fundingrequest, decided_funding, ReviewResult.Approved, remarks)

    def rejected(self, decided_funding: Money = Money(0, Currency.EUR), remarks: str = "") -> "Review":
        return Review(self.fundingrequest, decided_funding, ReviewResult.Rejected, remarks)

    def opened(self, decided_funding: Money | None = None, remarks: str = "") -> "Review":
        return Review(fundingrequest=self.fundingrequest, decided_funding=decided_funding if decided_funding is not None else self.decided_funding, result=ReviewResult.Open, remarks=remarks)

    def costs_waived(self, decided_funding: Money = Money(0, Currency.EUR), remarks: str = "") -> "Review":
        return Review(self.fundingrequest, decided_funding, ReviewResult.Waived, remarks)

    def closed(self, decided_funding: Money = Money(0, Currency.EUR), remarks: str = "") -> "Review":
        return Review(self.fundingrequest, decided_funding, ReviewResult.Closed, remarks)

    def with_remarks(self, remarks: str, decided_funding: Money = Money(0, Currency.EUR)) -> "Review":
        return Review(self.fundingrequest, decided_funding, self.result, remarks)

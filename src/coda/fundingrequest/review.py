import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coda.money import Currency, Money

if TYPE_CHECKING:
    from coda.fundingrequest import FundingRequestId


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

    def rejected(self, remarks: str = "") -> "Review":
        return Review(self.fundingrequest, result=ReviewResult.Rejected, remarks=remarks)

    def opened(self, remarks: str = "") -> "Review":
        return Review(self.fundingrequest, decided_funding=self.decided_funding, remarks=remarks)

    def costs_waived(self, remarks: str = "") -> "Review":
        return Review(self.fundingrequest, result=ReviewResult.Waived, remarks=remarks)

    def closed(self, remarks: str = "") -> "Review":
        return Review(self.fundingrequest, result=ReviewResult.Closed, remarks=remarks)

    def with_remarks(self, remarks: str) -> "Review":
        return Review(self.fundingrequest, self.decided_funding, self.result, remarks)

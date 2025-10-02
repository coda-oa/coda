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
    decided_funding: Money | None = field(default_factory=lambda: Money(0, Currency.EUR))
    result: ReviewResult | None = ReviewResult.Open
    remarks: str = ""

    def update_review(self, result: ReviewResult | None = None, decided_funding: Money | None = None, remarks: str = "") -> "Review":
        return Review(self.fundingrequest, self.decided_funding if decided_funding is None else decided_funding, self.result if result is None else result, remarks or self.remarks)
    


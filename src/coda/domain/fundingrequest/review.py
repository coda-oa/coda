import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from coda.domain.finance.invoice import FundingSourceId
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
class ReviewSplit:
    """Part of a decided funding amount attributed to one budget."""

    funding_source: FundingSourceId
    amount: Money


@dataclass(frozen=True)
class FundingSplits:
    """The funding splits attributed to budgets.

    Computes per-budget totals and the positive delta over totals already
    committed. Only the positive delta is a new commitment; an unchanged
    re-approval commits nothing."""

    splits: tuple[ReviewSplit, ...]

    @classmethod
    def of(cls, splits: Iterable[ReviewSplit]) -> "FundingSplits":
        return cls(tuple(splits))

    @classmethod
    def from_persisted(
        cls, rows: Iterable[tuple[FundingSourceId, Decimal]], currency: Currency
    ) -> "FundingSplits":
        """Builds splits from persisted rows.

        Persisted split rows carry no currency. The caller pins the currency.
        The save path validates it against each budget's currency."""
        return cls(
            tuple(
                ReviewSplit(FundingSourceId(source), Money(amount, currency))
                for source, amount in rows
            )
        )

    def totals(self) -> dict[FundingSourceId, Money]:
        """Sums the splits per funding source."""
        totals: dict[FundingSourceId, Money] = {}
        for split in self.splits:
            zero = Money(0, split.amount.currency)
            totals[split.funding_source] = totals.get(split.funding_source, zero) + split.amount
        return totals

    def sources(self) -> frozenset[FundingSourceId]:
        """The distinct funding sources the splits attribute to."""
        return frozenset(split.funding_source for split in self.splits)

    def positive_delta(
        self, own_totals: Mapping[FundingSourceId, Money]
    ) -> dict[FundingSourceId, Money]:
        """Computes the positive delta over the review's own committed totals.

        Per source: max(0, total - own total). A missing own total counts as
        zero. Returns only positive differences; unchanged re-approvals
        commit nothing."""
        deltas: dict[FundingSourceId, Money] = {}
        for source, new_total in self.totals().items():
            own = own_totals.get(source)
            delta = new_total if own is None else new_total - own
            if delta.amount > 0:
                deltas[source] = delta
        return deltas


@dataclass(frozen=True)
class DecidedFunding:
    """A review's decided funding amount together with the funding splits
    attributing it to budgets. The total and every split share one currency —
    the decided funding's."""

    total: Money
    splits: FundingSplits

    def __post_init__(self) -> None:
        if any(split.amount.currency != self.total.currency for split in self.splits.splits):
            raise ValueError("funding splits must be denominated in the decided funding's currency")

    def all_assigned(self) -> bool:
        return self.split_sum() == self.total

    def split_sum(self) -> Money:
        return sum(
            (split.amount for split in self.splits.splits), start=Money(0, self.total.currency)
        )

    def delta_over(self, persisted: FundingSplits) -> dict[FundingSourceId, Money]:
        """The positive delta of the splits over the persisted splits' totals
        — the capacity-checked commitment."""
        return self.splits.positive_delta(persisted.totals())


@dataclass(frozen=True)
class Review:
    fundingrequest: "FundingRequestId | None" = None
    decided_funding: Money = field(default_factory=lambda: Money(0, Currency.EUR))
    result: ReviewResult = ReviewResult.Open
    remarks: str = ""
    funding_splits: FundingSplits = FundingSplits(())

    def update_review(
        self,
        result: ReviewResult | None = None,
        decided_funding: Money | None = None,
        remarks: str = "",
        funding_splits: FundingSplits | None = None,
    ) -> "Review":
        return Review(
            self.fundingrequest,
            self.decided_funding if decided_funding is None else decided_funding,
            self.result if result is None else result,
            remarks or self.remarks,
            self.funding_splits if funding_splits is None else funding_splits,
        )

from decimal import Decimal

import pytest

from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.review import DecidedFunding, FundingSplits, ReviewSplit
from coda.domain.money import Currency, Money


def _split(source: int, amount: str) -> ReviewSplit:
    return ReviewSplit(FundingSourceId(source), Money(Decimal(amount), Currency.EUR))


def test__decided_funding__rejects_splits_in_other_currency() -> None:
    """The decided funding and its splits share one currency: a split pinned
    to another currency is a construction error, not a silent mix."""
    stale_split = ReviewSplit(FundingSourceId(1), Money(Decimal(100), Currency.SEK))

    with pytest.raises(ValueError):
        DecidedFunding(Money(Decimal(100), Currency.EUR), FundingSplits.of([stale_split]))


def test__totals__sums_per_funding_source() -> None:
    splits = FundingSplits.of([_split(1, "100"), _split(2, "50"), _split(1, "25")])

    totals = splits.totals()

    assert totals == {
        FundingSourceId(1): Money(Decimal(125), Currency.EUR),
        FundingSourceId(2): Money(Decimal(50), Currency.EUR),
    }


def test__positive_delta__returns_only_positive_differences_and_missing_own_is_zero() -> None:
    splits = FundingSplits.of([_split(1, "100"), _split(2, "50"), _split(3, "30")])
    own = {
        FundingSourceId(1): Money(Decimal(70), Currency.EUR),
        FundingSourceId(2): Money(Decimal(50), Currency.EUR),
    }

    deltas = splits.positive_delta(own)

    assert deltas == {
        FundingSourceId(1): Money(Decimal(30), Currency.EUR),
        # source 2: unchanged (delta 0) — not returned
        # source 3: missing own total counts as zero
        FundingSourceId(3): Money(Decimal(30), Currency.EUR),
    }


def test__sources__returns_distinct_funding_sources() -> None:
    splits = FundingSplits.of([_split(1, "100"), _split(2, "50"), _split(1, "25")])

    assert splits.sources() == {FundingSourceId(1), FundingSourceId(2)}


def test__from_persisted__attaches_given_currency_to_currencyless_rows() -> None:
    splits = FundingSplits.from_persisted(
        [(FundingSourceId(1), Decimal(100)), (FundingSourceId(2), Decimal(20))], Currency.SEK
    )

    assert splits.splits == (
        ReviewSplit(FundingSourceId(1), Money(Decimal(100), Currency.SEK)),
        ReviewSplit(FundingSourceId(2), Money(Decimal(20), Currency.SEK)),
    )
    assert splits.totals() == {
        FundingSourceId(1): Money(Decimal(100), Currency.SEK),
        FundingSourceId(2): Money(Decimal(20), Currency.SEK),
    }

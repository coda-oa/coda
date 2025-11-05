from decimal import Decimal

import pytest

from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.invoice_positions import (
    AnyPosition,
    FundingAssignment,
    InvalidSplitAmount,
    PublicationItem,
)
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId


def make_sut(
    funding_source: FundingSourceId | None = None, amount: Decimal = Decimal(100)
) -> AnyPosition:
    sut = invoice_positions.create(
        item=PublicationItem(
            PublicationId(1),
            cost_type=PublicationCostType.Gold_OA,
        ),
        cost=Money(amount, Currency.EUR),
        funding_source=funding_source,
        tax_rate=TaxRate.from_percentage(0),
    )
    return sut


def test__position__split_costs__no_remaining_costs() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(70))

    assert sut.funding_assignments() == [
        FundingAssignment(None, Money(30, Currency.EUR)),
        FundingAssignment(FundingSourceId(1), Money(70, Currency.EUR)),
    ]


def test__position_with_funding_source__split_costs__first_participant_has_funding_source() -> None:
    funding_source = FundingSourceId(99)
    sut = make_sut(funding_source)

    sut.assign_funding(FundingSourceId(1), Decimal(70))

    assert sut.funding_assignments() == [
        FundingAssignment(funding_source, Money(30, Currency.EUR)),
        FundingAssignment(FundingSourceId(1), Money(70, Currency.EUR)),
    ]


def test__position_is_split__split_again__splits_among_three_participants() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(70))
    sut.assign_funding(FundingSourceId(2), Decimal(20))

    assert sut.funding_assignments() == [
        FundingAssignment(None, Money(10, Currency.EUR)),
        FundingAssignment(FundingSourceId(1), Money(70, Currency.EUR)),
        FundingAssignment(FundingSourceId(2), Money(20, Currency.EUR)),
    ]


@pytest.mark.parametrize("amount", (101, 100), ids=("greater", "equal"))
def test__position__split_costs__split_must_not_be_greater_than_amount(amount: int) -> None:
    sut = make_sut()

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(amount))


@pytest.mark.parametrize("amount", (-101, -100), ids=("greater", "equal"))
def test__position_with_negative_amount__split_costs__split_must_not_be_greater_than_amount(
    amount: int,
) -> None:
    sut = make_sut(amount=Decimal(-100))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(amount))


@pytest.mark.parametrize("amount", (31, 30), ids=("greater", "equal"))
def test__position_is_split__split_greater_than_remaining__raises_error(amount: int) -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(70))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(2), Decimal(amount))


def test__position_with_positive_amount__split_negative_amount__is_not_allowed() -> None:
    sut = make_sut()

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(-1))


def test__position_with_negative_amount__split_positive_amount__is_not_allowed() -> None:
    sut = make_sut(amount=Decimal(-100))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(1))

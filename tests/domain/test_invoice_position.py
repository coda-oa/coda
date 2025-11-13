from decimal import Decimal

import pytest

from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.invoice_positions import (
    Position,
    FundingAssignment,
    InvalidSplitAmount,
    PublicationItem,
)
from coda.domain.finance.taxable_money import CostBasis, NetMoney
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId


def make_sut(
    funding_source: FundingSourceId | None = None, amount: Decimal = Decimal(100)
) -> Position:
    sut = invoice_positions.create(
        item=PublicationItem(
            PublicationId(1),
            cost_type=PublicationCostType.Gold_OA,
        ),
        cost=NetMoney(amount, Currency.EUR, TaxRate.from_percentage(19)),
        funding_source=funding_source,
    )
    return sut


def make_vat(amount: Decimal = Decimal(100)) -> Position:
    return invoice_positions.create(
        item=PublicationItem(PublicationId(1), PublicationCostType.Vat),
        cost=NetMoney(amount, Currency.EUR, TaxRate.from_percentage(19)),
    )


def test__position__equals_other_position_with_same_data() -> None:
    first = make_sut(FundingSourceId(1), amount=Decimal(12.50))
    first.assign_funding(FundingSourceId(2), Decimal(5))

    second = make_sut(FundingSourceId(1), amount=Decimal(12.50))
    second.assign_funding(FundingSourceId(2), Decimal(5))

    other_amount = make_sut(amount=Decimal(30))

    other_funding = make_sut(FundingSourceId(1), amount=Decimal(12.50))
    other_funding.assign_funding(FundingSourceId(2), Decimal(3))

    assert first == second
    assert first != other_amount
    assert first != other_funding


def test__position__no_costs_assigned_explicitly__no_unassigned_costs() -> None:
    sut = make_sut()

    assert sut.unassigned_costs() == Money(0, Currency.EUR)


def test__position__all_costs_assigned__no_remaining_costs() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(100))

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(FundingSourceId(1), Money(100, Currency.EUR)),
    ]


def test__position__all_costs_assigned_as_net_and_gross__no_remaining_costs() -> None:
    sut = make_sut(amount=Decimal("5000.00"))

    sut.assign_funding(FundingSourceId(1), Decimal("2000.00"), CostBasis.gross)
    sut.assign_funding(FundingSourceId(2), Decimal("3319.33"), CostBasis.net)

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(FundingSourceId(1), Money("1680.6722689076", Currency.EUR)),
        FundingAssignment(FundingSourceId(2), Money("3319.33", Currency.EUR)),
    ]


def test__vat_position__all_costs_assigned__assignments_do_not_change_for_tax_mode() -> None:
    sut = make_vat()

    sut.assign_funding(FundingSourceId(1), Decimal(30), CostBasis.gross)
    sut.assign_funding(FundingSourceId(2), Decimal(70), CostBasis.net)

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(FundingSourceId(1), Money(30, Currency.EUR)),
        FundingAssignment(FundingSourceId(2), Money(70, Currency.EUR)),
    ]
    assert sut.unassigned_costs(CostBasis.net) == sut.unassigned_costs(CostBasis.gross)
    assert sut.funding_assignments(CostBasis.net) == sut.funding_assignments(CostBasis.gross)


def test__position__all_costs_assigned__can_retrieve_assignments_as_gross() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(20))
    sut.assign_funding(FundingSourceId(2), Decimal(80))

    assert sut.funding_assignments(CostBasis.gross) == [
        FundingAssignment(FundingSourceId(1), Money("23.8", Currency.EUR)),
        FundingAssignment(FundingSourceId(2), Money("95.2", Currency.EUR)),
    ]


def test__position__costs_assigned_partially__has_unassigned_costs() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(30))

    assert sut.unassigned_costs() == Money(70, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(FundingSourceId(1), Money(30, Currency.EUR)),
    ]


def test__postion__partially_assigned_costs__can_retrieve_unassigned_costs_as_gross() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(50))

    assert sut.unassigned_costs(CostBasis.gross) == Money("59.50", Currency.EUR)


def test__position__assigned_all_costs_between_multiple_funding_sources__no_unassigned_costs() -> (
    None
):
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(70))
    sut.assign_funding(FundingSourceId(2), Decimal(30))

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(FundingSourceId(1), Money(70, Currency.EUR)),
        FundingAssignment(FundingSourceId(2), Money(30, Currency.EUR)),
    ]


def test__position__partially_assigned_costs_between_multiple_sources__has_unassigned_costs() -> (
    None
):
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(20))
    sut.assign_funding(FundingSourceId(2), Decimal(30))

    assert sut.unassigned_costs() == Money(50, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(FundingSourceId(1), Money(20, Currency.EUR)),
        FundingAssignment(FundingSourceId(2), Money(30, Currency.EUR)),
    ]


def test__position__split_costs__split_must_not_be_greater_than_amount() -> None:
    sut = make_sut()

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(101))


def test__position_with_negative_amount__split_costs__split_must_not_be_greater_than_amount() -> (
    None
):
    sut = make_sut(amount=Decimal(-100))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(-101))


def test__position_is_split__split_greater_than_remaining__raises_error() -> None:
    sut = make_sut()

    sut.assign_funding(FundingSourceId(1), Decimal(70))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(2), Decimal(31))


def test__position_with_positive_amount__split_negative_amount__is_not_allowed() -> None:
    sut = make_sut()

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(-1))


def test__position_with_negative_amount__split_positive_amount__is_not_allowed() -> None:
    sut = make_sut(amount=Decimal(-100))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(FundingSourceId(1), Decimal(1))

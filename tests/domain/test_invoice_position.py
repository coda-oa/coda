from decimal import Decimal

import pytest

from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.invoice_positions import (
    FundingAssignment,
    InvalidSplitAmount,
    PartialAssignment,
    Position,
    PublicationItem,
)
from coda.domain.finance.taxable_money import CostBasis
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId
from tests import domainfactory


def make_sut(amount: Decimal = Decimal(100)) -> Position:
    sut = invoice_positions.create(
        item=PublicationItem(
            PublicationId(1),
            cost_type=PublicationCostType.Gold_OA,
        ),
        cost=Money(amount, Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    return sut


def make_vat(amount: Decimal = Decimal(100)) -> Position:
    return invoice_positions.create(
        item=PublicationItem(PublicationId(1), PublicationCostType.Vat),
        cost=Money(amount, Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )


def test__position__equals_other_position_with_same_data() -> None:
    first = make_sut(amount=Decimal(12.50))

    first_budget = Budget(FundingSourceId(2), "my-budget")
    first.assign_funding(first_budget, Decimal(5))

    second = make_sut(amount=Decimal(12.50))
    second_budget = Budget(FundingSourceId(2), "my-budget")
    second.assign_funding(second_budget, Decimal(5))

    other_amount = make_sut(amount=Decimal(30))

    other_funding = make_sut(amount=Decimal(12.50))
    other_budget = Budget(FundingSourceId(2), "my-budget")
    other_funding.assign_funding(other_budget, Decimal(3))

    assert first == second
    assert first != other_amount
    assert first != other_funding


def test__position__no_costs_assigned_explicitly__no_unassigned_costs() -> None:
    sut = make_sut()

    assert sut.unassigned_costs() == Money(0, Currency.EUR)


def test__position__all_costs_assigned__no_remaining_costs() -> None:
    sut = make_sut()
    budget = domainfactory.budget(FundingSourceId(1))

    sut.assign_funding(budget, Decimal(100))

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget, Money(100, Currency.EUR)),
    ]


def test__position__all_costs_assigned_as_net_and_gross__no_remaining_costs() -> None:
    sut = make_sut(amount=Decimal("5000.00"))
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_funding(budget_1, Decimal("2000.00"), CostBasis.gross)
    sut.assign_funding(budget_2, Decimal("3319.33"), CostBasis.net)

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money("1680.6722689076", Currency.EUR)),
        FundingAssignment(budget_2, Money("3319.33", Currency.EUR)),
    ]


def test__vat_position__all_costs_assigned__assignments_do_not_change_for_tax_mode() -> None:
    sut = make_vat()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_funding(budget_1, Decimal(30), CostBasis.gross)
    sut.assign_funding(budget_2, Decimal(70), CostBasis.net)

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money(30, Currency.EUR)),
        FundingAssignment(budget_2, Money(70, Currency.EUR)),
    ]
    assert sut.unassigned_costs(CostBasis.net) == sut.unassigned_costs(CostBasis.gross)
    assert sut.funding_assignments(CostBasis.net) == sut.funding_assignments(CostBasis.gross)


def test__position__all_costs_assigned__can_retrieve_assignments_as_gross() -> None:
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_funding(budget_1, Decimal(20))
    sut.assign_funding(budget_2, Decimal(80))

    assert sut.funding_assignments(CostBasis.gross) == [
        FundingAssignment(budget_1, Money("23.8", Currency.EUR)),
        FundingAssignment(budget_2, Money("95.2", Currency.EUR)),
    ]


def test__position__costs_assigned_partially__has_unassigned_costs() -> None:
    sut = make_sut()
    budget = domainfactory.budget(FundingSourceId(1))

    sut.assign_funding(budget, Decimal(30))

    assert sut.unassigned_costs() == Money(70, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget, Money(30, Currency.EUR)),
    ]


def test__postion__partially_assigned_costs__can_retrieve_unassigned_costs_as_gross() -> None:
    sut = make_sut()
    budget = domainfactory.budget(FundingSourceId(1))

    sut.assign_funding(budget, Decimal(50))

    assert sut.unassigned_costs(CostBasis.gross) == Money("59.50", Currency.EUR)


def test__position__assigned_all_costs_between_multiple_funding_sources__no_unassigned_costs() -> (
    None
):
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_funding(budget_1, Decimal(70))
    sut.assign_funding(budget_2, Decimal(30))

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money(70, Currency.EUR)),
        FundingAssignment(budget_2, Money(30, Currency.EUR)),
    ]


def test__position__partially_assigned_costs_between_multiple_sources__has_unassigned_costs() -> (
    None
):
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_funding(budget_1, Decimal(20))
    sut.assign_funding(budget_2, Decimal(30))

    assert sut.unassigned_costs() == Money(50, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money(20, Currency.EUR)),
        FundingAssignment(budget_2, Money(30, Currency.EUR)),
    ]


def test__position__split_costs__split_must_not_be_greater_than_amount() -> None:
    sut = make_sut()

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(domainfactory.budget(), Decimal(101))


def test__position_with_negative_amount__split_costs__split_must_not_be_greater_than_amount() -> (
    None
):
    sut = make_sut(amount=Decimal(-100))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(domainfactory.budget(), Decimal(-101))


def test__position_is_split__split_greater_than_remaining__raises_error() -> None:
    sut = make_sut()

    sut.assign_funding(domainfactory.budget(), Decimal(70))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(domainfactory.budget(), Decimal(31))


def test__position_with_positive_amount__split_negative_amount__is_not_allowed() -> None:
    sut = make_sut()

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(domainfactory.budget(), Decimal(-1))


def test__position_with_negative_amount__split_positive_amount__is_not_allowed() -> None:
    sut = make_sut(amount=Decimal(-100))

    with pytest.raises(InvalidSplitAmount):
        sut.assign_funding(domainfactory.budget(), Decimal(1))


def test__position_without_assignments__assign_remaining__assigns_everything_to_funding_source() -> (
    None
):
    sut = make_sut()
    budget = domainfactory.budget(FundingSourceId(1))

    sut.assign_remaining(budget)

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [FundingAssignment(budget, Money(100, Currency.EUR))]


def test__position_with_partial_assignment__assign_remaining__assigns_rest_to_funding_source() -> (
    None
):
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_funding(budget_1, Decimal("73.24"))
    sut.assign_remaining(budget_2)

    assert sut.unassigned_costs() == Money(0, Currency.EUR)
    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money("73.24", Currency.EUR)),
        FundingAssignment(budget_2, Money("26.76", Currency.EUR)),
    ]


def test__position_all_funding_assigned__assign_remaining__does_not_change_assignments() -> None:
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut.assign_remaining(budget_1)

    sut.assign_remaining(budget_2)

    assert sut.funding_assignments() == [FundingAssignment(budget_1, Money(100, Currency.EUR))]


def test__position__assign_partial_assignments_explicitly__has_corresponding_funding_assignments() -> (
    None
):
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    assignments = [
        PartialAssignment(budget_1, Decimal(30)),
        PartialAssignment(budget_2, Decimal(70)),
    ]
    sut.assign_many(assignments)

    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money(30, Currency.EUR)),
        FundingAssignment(budget_2, Money(70, Currency.EUR)),
    ]


def test__position__assign_partial_assignments_implicitly__splits_everything_evenly() -> None:
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    assignments = [
        PartialAssignment(budget_1),
        PartialAssignment(budget_2),
    ]
    sut.assign_many(assignments)

    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money(50, Currency.EUR)),
        FundingAssignment(budget_2, Money(50, Currency.EUR)),
    ]


def test__position__assign_partial_assignments_mixed__splits_implicit_remaining_amount_between_implicit_assignments() -> (
    None
):
    sut = make_sut()
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))
    budget_3 = domainfactory.budget(FundingSourceId(3))

    assignments = [
        PartialAssignment(budget_1),
        PartialAssignment(budget_2, Decimal(20)),
        PartialAssignment(budget_3),
    ]
    sut.assign_many(assignments)

    assert sut.funding_assignments() == [
        FundingAssignment(budget_1, Money(40, Currency.EUR)),
        FundingAssignment(budget_2, Money(20, Currency.EUR)),
        FundingAssignment(budget_3, Money(40, Currency.EUR)),
    ]


def test__position_with_assignments__convert_to_different_currency__converts_assignments() -> None:
    budget_1 = domainfactory.budget(FundingSourceId(1))
    budget_2 = domainfactory.budget(FundingSourceId(2))

    sut = make_sut()

    sut.assign_funding(budget_1, Decimal(20))
    sut.assign_funding(budget_2, Decimal(80))

    def exchange(origin: Currency, target: Currency) -> Decimal:
        _, _ = origin, target
        return Decimal(2)

    actual = sut.convert(Currency.USD, exchange)

    assert actual.funding_assignments() == [
        FundingAssignment(budget_1, Money(40, Currency.USD)),
        FundingAssignment(budget_2, Money(160, Currency.USD)),
    ]

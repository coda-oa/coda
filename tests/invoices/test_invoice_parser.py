from collections.abc import Callable
from decimal import Decimal
from typing import cast

import pytest

from coda.apps.contracts import repository
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.dto.edit_position_dtos import FundingAssignmentDto
from coda.contexts.finance.services import invoice_parser
from coda.domain.author import InstitutionId
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice_positions import FundingAssignment, Position
from coda.domain.finance.taxable_money import CostBasis
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory


def contract_year() -> ContractYear:
    contract = domainfactory.contract()
    contract.id = repository.create(contract)
    return contract.in_first_year()


def publication_position(cost_type: PublicationCostType) -> Position:
    return domainfactory.publication_position(
        PublicationId(modelfactory.publication().pk), cost_type=cost_type
    )


def contract_position(cost_type: ContractCostType) -> Position:
    return domainfactory.contract_position(contract_year(), cost_type=cost_type)


def free_position(cost_type: PublicationCostType) -> Position:
    return domainfactory.free_position(cost_type=cost_type)


Positions = (
    lambda: publication_position(PublicationCostType.Gold_OA),
    lambda: contract_position(ContractCostType.Publish),
    lambda: free_position(PublicationCostType.Permission),
)

VatPositions = (
    lambda: publication_position(PublicationCostType.Vat),
    lambda: contract_position(ContractCostType.Vat),
    lambda: free_position(PublicationCostType.Vat),
)


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__converting_position_to_dto_and_back__return_same_position(
    create_position: Callable[[], Position],
) -> None:
    before = create_position()

    dto = invoice_parser.position_to_dto(before)
    after = invoice_parser.to_position(dto, before.cost.currency)

    assert before == after
    assert before.net() == after.net()
    assert before.tax() == after.tax()
    assert before.total() == after.total()


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", VatPositions)
def test__vat_position__converted_to_dto__has_only_tax_amount(
    create_position: Callable[[], Position],
) -> None:
    position = create_position()

    dto = invoice_parser.position_to_dto(position)

    assert dto.cost_amount == position.tax().amount
    assert dto.tax_rate == Decimal(0)


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_with_funding_assignments__convert_to_dto_and_back__keeps_assignments(
    create_position: Callable[[], Position],
) -> None:
    institution = modelfactory.institution()
    funding_source = domainfactory.budget()
    funding_source.id = funding_source_repository.create(funding_source)
    funding_source_2 = SplitSource.new(InstitutionId(institution.pk), institution.name)
    position = create_position()

    position.assign_funding(funding_source, position.net().amount / 2)
    position.assign_remaining(funding_source_2)

    dto = invoice_parser.position_to_dto(position)

    actual = invoice_parser.to_position(dto, currency=position.cost.currency)

    assert position == actual


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_with_funding_assignments__convert_to_dto__dto_contains_unassigned_costs(
    create_position: Callable[[], Position],
) -> None:
    funding_source = domainfactory.budget()
    funding_source.id = funding_source_repository.create(funding_source)
    position = create_position()

    less = position.net().amount - 1
    position.assign_funding(funding_source, less)

    dto = invoice_parser.position_to_dto(position)

    assert dto.unassigned_costs == Decimal(1)


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_dto_with_empty_funding_assignment__does_not_assign_to_domain_object(
    create_position: Callable[[], Position],
) -> None:
    position = create_position()
    dto = invoice_parser.position_to_dto(position)

    dto.funding_assignments.append(FundingAssignmentDto())

    assert invoice_parser.to_position(dto, position.cost.currency) == position


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_with_funding_assignment__convert_to_dto__contains_budget_type(
    create_position: Callable[[], Position],
) -> None:
    institution = InstitutionId(modelfactory.institution().pk)
    funding_source = SplitSource.new(institution, "some-name")
    funding_source.id = funding_source_repository.create(funding_source)

    position = create_position()
    position.assign_remaining(funding_source)

    dto = invoice_parser.position_to_dto(position)

    funding_assignment = dto.funding_assignments[0]
    assert funding_assignment.funding_source_type == "institution"


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_dto_with_funding_assignment_in_gross__convert_to_position__position_has_funding_assignments(
    create_position: Callable[[], Position],
) -> None:
    budget = Budget.new("my budget")
    budget.id = funding_source_repository.create(budget)

    position = create_position()
    dto = invoice_parser.position_to_dto(position)

    total = position.total().amount
    dto.cost_basis_mode = CostBasis.gross
    dto.funding_assignments.append(FundingAssignmentDto(funding_source=budget.id, amount=total))

    actual = invoice_parser.to_position(dto, position.cost.currency)

    assert actual.funding_assignments(CostBasis.gross) == [
        FundingAssignment(budget, position.total())
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_with_funding_assignments__convert_to_dto_as_gross__returns_dto_with_assignments_as_gross(
    create_position: Callable[[], Position],
) -> None:
    budget_1 = Budget.new("my budget")
    budget_1.id = funding_source_repository.create(budget_1)
    budget_2 = Budget.new("another budget")
    budget_2.id = funding_source_repository.create(budget_2)

    position = create_position()
    position.assign_funding(budget_1, position.net().amount / 3)
    position.assign_funding(budget_1, position.net().amount / 3)

    dto = invoice_parser.position_to_dto(position, CostBasis.gross)

    assert dto.cost_basis_mode == CostBasis.gross
    assert dto.funding_assignments == [
        FundingAssignmentDto(
            funding_source=cast(FundingSource, fa.funding_source).id,
            amount=fa.amount.amount,
        )
        for fa in position.funding_assignments(CostBasis.gross)
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_with_unassigned_costs__convert_to_dto_as_gross__returns_dto_unassigned_costs_as_gross(
    create_position: Callable[[], Position],
) -> None:
    budget = Budget.new("my budget")
    budget.id = funding_source_repository.create(budget)

    position = create_position()
    position.assign_funding(budget, position.total().amount / 2, CostBasis.gross)

    dto = invoice_parser.position_to_dto(position, CostBasis.gross)

    assert dto.unassigned_costs == position.unassigned_costs(CostBasis.gross).amount


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
def test__position_dto_with_unspecified_funding_source_in_assignment__converts_to_none_funding_source(
    create_position: Callable[[], Position],
) -> None:
    position = create_position()
    position.assign_remaining(None)

    dto = invoice_parser.position_to_dto(position)
    assert dto.funding_assignments[0].funding_source is None

    position = invoice_parser.to_position(dto, position.cost.currency)
    assert position.funding_assignments()[0].funding_source is None


def _budget() -> Budget:
    budget = domainfactory.budget()
    budget.id = funding_source_repository.create(budget)
    return budget


def _institution() -> SplitSource:
    return domainfactory.split_source(InstitutionId(modelfactory.institution().pk))


FundingSources = (_budget, _institution)


@pytest.mark.django_db
@pytest.mark.parametrize("create_position", Positions)
@pytest.mark.parametrize("create_funding_source", FundingSources)
def test__position_dto_with_amount_all_and_selected_funding_source__assigns_full_cost_to_selected_budget(
    create_position: Callable[[], Position],
    create_funding_source: Callable[[], FundingSource],
) -> None:
    """
    When a funding assignment has amount="all" (from STATE 1 implicit assignment template)
    and a budget is selected, the parser should assign the full cost to that budget.

    This tests the bug where DecimalOrDefault converts "all" to Decimal(0), causing
    the parser to create an invalid assignment with the selected budget but zero amount.
    The correct behavior is to assign the full cost to the selected budget.
    """
    funding_source = create_funding_source()

    position = create_position()
    dto = invoice_parser.position_to_dto(position)

    dto.funding_assignments.append(
        FundingAssignmentDto(
            funding_source=funding_source.identity(),
            funding_source_type=funding_source.kind(),
            amount="all",
        )
    )

    parsed_position = invoice_parser.to_position(dto, position.cost.currency)

    assert len(parsed_position.funding_assignments()) == 1
    assignment = parsed_position.funding_assignments()[0]
    assert assignment.funding_source is not None
    assert assignment.funding_source.identity() == funding_source.identity()
    assert assignment.amount == position.net()
    assert parsed_position.unassigned_costs().amount == Decimal(0)

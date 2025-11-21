from collections.abc import Callable
from decimal import Decimal

import pytest

from coda.apps.contracts import repository
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.dto.edit_position_dtos import FundingAssignmentDto
from coda.contexts.finance.services import invoice_parser
from coda.domain.author import InstitutionId
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import SplitSource
from coda.domain.finance.invoice_positions import Position
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

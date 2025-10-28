from collections.abc import Callable
from decimal import Decimal

import pytest

from coda.apps.contracts import repository
from coda.contexts.finance.services import invoice_parser
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice_positions import AnyPosition
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory


def contract_year() -> ContractYear:
    contract = domainfactory.contract()
    contract.id = repository.create(contract)
    return contract.in_first_year()


def publication_position(cost_type: PublicationCostType) -> AnyPosition:
    return domainfactory.publication_position(
        PublicationId(modelfactory.publication().pk), cost_type=cost_type
    )


def contract_position(cost_type: ContractCostType) -> AnyPosition:
    return domainfactory.contract_position(contract_year(), cost_type=cost_type)


def free_position(cost_type: PublicationCostType) -> AnyPosition:
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
    create_position: Callable[[], AnyPosition],
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
    create_position: Callable[[], AnyPosition],
) -> None:
    position = create_position()

    dto = invoice_parser.position_to_dto(position)

    assert dto.cost_amount == position.tax().amount
    assert dto.tax_rate == Decimal(0)

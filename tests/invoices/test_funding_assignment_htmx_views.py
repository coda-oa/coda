from decimal import Decimal
from typing import cast
from django.template.response import TemplateResponse
import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.dto.edit_position_dtos import PositionDto, PositionList
from coda.contexts.finance.services import invoice_parser
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency
from coda.domain.money._money import Money
from tests import domainfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_initial_assignment__assigns_all_costs_to_new_assignment(client: Client) -> None:
    position = domainfactory.free_position(Currency.EUR)
    dto = invoice_parser.position_to_dto(position)

    response = add_funding_assignment(client, PositionList(positions=[dto]))

    actual: PositionDto = response.context["position"]
    assert_has_one_assignment_with_all_costs(actual, position.cost.amount)


def add_funding_assignment(client: Client, position_list: PositionList) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:position_add_funding_assignment"),
            {
                "currency": "EUR",
                "position_index": "1",
            }
            | formdata.map_to_dict(position_list),
        ),
    )


def assert_has_one_assignment_with_all_costs(position: PositionDto, expected_cost: Decimal) -> None:
    assert len(position.funding_assignments) == 1
    assert position.funding_assignments[0].amount == expected_cost
    assert position.unassigned_costs == Decimal("0.00")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_second_funding_assignment__has_remaining_costs(client: Client) -> None:
    budget = domainfactory.budget()
    budget.id = funding_source_repository.create(budget)
    position = invoice_positions.create(
        invoice_positions.FreeItem("some-item", PublicationCostType.Other),
        Money(100, Currency.EUR),
        TaxRate(0),
    )
    position.assign_funding(budget, Decimal(60))
    position_dto = invoice_parser.position_to_dto(position)
    position_list = PositionList(positions=[position_dto])

    response = add_funding_assignment(client, position_list)

    actual = response.context["position"]
    assert_all_costs_assigned(actual, Decimal("60.00"), Decimal("40.00"))


def assert_all_costs_assigned(position: PositionDto, *partial_assignments: Decimal) -> None:
    assert len(position.funding_assignments) == len(partial_assignments)
    assert tuple(f.amount for f in position.funding_assignments) == tuple(partial_assignments)
    assert position.unassigned_costs == Decimal("0.00")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__all_costs_assigned_in_first_assignment__add_second_assignment__defaults_to_zero(
    client: Client,
) -> None:
    budget = Budget.new("my budget")
    budget.id = funding_source_repository.create(budget)

    position = domainfactory.free_position(Currency.EUR)
    position.assign_remaining(budget)
    dto = invoice_parser.position_to_dto(position)

    response = add_funding_assignment(client, PositionList(positions=[dto]))

    actual: PositionDto = response.context["position"]
    assert len(actual.funding_assignments) == 2
    assert actual.funding_assignments[1].amount == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__two_funding_assignments__remove_first__only_has_second_assignment(client: Client) -> None:
    budget = Budget.new("my budget")
    budget.id = funding_source_repository.create(budget)

    position = domainfactory.free_position(Currency.EUR)
    position.assign_funding(None, Decimal(position.cost.amount) / 2)
    position.assign_remaining(budget)
    dto = invoice_parser.position_to_dto(position)

    response = remove_funding_assignment(client, PositionList(positions=[dto]), 1)

    last_assignment = position.funding_assignments()[-1]
    actual: PositionDto = response.context["position"]

    assert last_assignment.funding_source is not None
    assert len(actual.funding_assignments) == 1
    assert actual.funding_assignments[0].funding_source == last_assignment.funding_source.id
    assert actual.funding_assignments[0].amount == position.funding_assignments()[-1].amount.amount


def remove_funding_assignment(
    client: Client, position_list: PositionList, assgnment_index: int
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:position_remove_funding_assignment"),
            formdata.map_to_dict(position_list)
            | {
                "position_index": 1,
                "assignment_index": f"{assgnment_index}",
                "currency": "EUR",
            },
        ),
    )

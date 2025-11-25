from decimal import Decimal
from typing import cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.invoices import funding_source_repository, repository
from coda.contexts.finance.dto.edit_position_dtos import (
    FreeItemDto,
    FundingAssignmentDto,
    PositionDto,
    PositionList,
)
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.contexts.finance.services import invoice_parser, invoice_service
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import SplitSource
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.money import Currency
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_invoice_with_positions_with_split_costs__saves_to_db(client: Client) -> None:
    institution = modelfactory.institution()
    funding_source_1 = domainfactory.budget()
    funding_source_2 = SplitSource.new(InstitutionId(institution.pk), institution.name)
    funding_source_1.id = funding_source_repository.create(funding_source_1)
    funding_source_2.id = funding_source_repository.create(funding_source_2)

    creditor = CreditorId(modelfactory.creditor().pk)

    position = domainfactory.free_position(Currency.EUR)
    position.assign_funding(funding_source_1, Decimal(position.cost.amount) / Decimal(3))
    position.assign_funding(funding_source_2, Decimal(position.cost.amount) / Decimal(3))

    expected = domainfactory.invoice(creditor=creditor, positions=[])
    expected.reset_payment()
    expected.positions = [position]

    _invoice_head = invoice_head(expected)
    position_dto = PositionList(positions=[invoice_parser.position_to_dto(position)])

    _ = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(_invoice_head)
        | formdata.map_to_dict(position_dto),
    )

    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__existing_invoice__update_with_positions_with_split_costs__saves_to_db(
    client: Client,
) -> None:
    institution = modelfactory.institution()
    funding_source_1 = domainfactory.budget()
    funding_source_2 = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    funding_source_1.id = funding_source_repository.create(funding_source_1)
    funding_source_2.id = funding_source_repository.create(funding_source_2)

    creditor = CreditorId(modelfactory.creditor().pk)

    position = domainfactory.free_position(Currency.EUR)
    expected = domainfactory.invoice(creditor=creditor, positions=[])
    expected.reset_payment()
    expected.positions = [position]
    expected.id = invoice_service.save(expected)

    position.assign_funding(funding_source_1, Decimal(position.cost.amount) / Decimal(3))
    position.assign_funding(funding_source_2, Decimal(position.cost.amount) / Decimal(3))

    _invoice_head = invoice_head(expected)
    position_dto = PositionList(positions=[invoice_parser.position_to_dto(position)])

    _ = client.post(
        reverse("invoices:update", kwargs={"pk": expected.id}),
        {"action": "create"}
        | formdata.map_to_dict(_invoice_head)
        | formdata.map_to_dict(position_dto),
    )

    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_invoice_with_empty_funding_assignments__assigns_all_to_single_source(
    client: Client,
) -> None:
    creditor = CreditorId(modelfactory.creditor().pk)
    position = domainfactory.free_position(Currency.EUR)
    expected = domainfactory.invoice(creditor=creditor, positions=[])
    expected.reset_payment()
    expected.positions = [position]

    position_dto = invoice_parser.position_to_dto(position)
    position_dto.funding_assignments.append(FundingAssignmentDto())
    position_list = PositionList(positions=[position_dto])
    _invoice_head = invoice_head(expected)

    _ = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(_invoice_head)
        | formdata.map_to_dict(position_list),
    )

    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(actual, expected)


def invoice_head(expected: Invoice) -> InvoiceHeadDto:
    return InvoiceHeadDto(
        number=expected.number,
        date=expected.date,
        creditor=expected.creditor,
        currency=expected.currency(),
        external_invoice_id=expected.external_invoice_id,
        status=expected.status,
        comment=expected.comment,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_first_funding_assignment__amount_is_prefilled_with_full_position_cost(
    client: Client,
) -> None:
    """Test STATE 1 → STATE 2 transition.

    Clicking 'Add' on a position with no funding assignments creates exactly ONE
    funding assignment with the full position cost pre-filled, showing:
    - Dropdowns for funding source type and funding source
    - Visible amount field (key difference from implicit state)
    - NO remove button (key difference from multi-explicit state)

    This is a regression test for bugs where:
    1. Two funding assignment rows appeared instead of one
    2. The first funding assignment had amount=0 instead of the full position cost
    """
    modelfactory.creditor()
    modelfactory.budget()
    position_dto = PositionDto(
        item=FreeItemDto(description="Test Item", cost_type="gold-oa"),
        cost_amount=Decimal("100.00"),
        tax_rate=Decimal("19"),
    )
    position_list = PositionList(positions=[position_dto])

    response = add_funding_assignment(client, position_list)

    position = response.context["position"]
    assert_has_one_assignment_with_all_costs(position)


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


def assert_has_one_assignment_with_all_costs(position: PositionDto) -> None:
    assert len(position.funding_assignments) == 1
    assert position.funding_assignments[0].amount == Decimal("100.00")
    assert position.unassigned_costs == Decimal("0.00")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_second_funding_assignment__transitions_to_multi_explicit_mode(
    client: Client,
) -> None:
    """
    Clicking 'Add' when one funding assignment exists should:
    1. Keep the existing assignment
    2. Add a second assignment with remaining unassigned costs
    3. Show remove buttons on BOTH assignments (transition to multi-explicit mode)
    """
    modelfactory.creditor()
    modelfactory.budget()
    position_dto = PositionDto(
        item=FreeItemDto(description="Test Item", cost_type="gold-oa"),
        cost_amount=Decimal("100.00"),
        tax_rate=Decimal("19"),
        funding_assignments=[
            FundingAssignmentDto(amount=Decimal("60.00"), funding_source_type="budget")
        ],
    )
    position_list = PositionList(positions=[position_dto])

    response = add_funding_assignment(client, position_list)

    position = response.context["position"]
    assert_all_costs_assigned(position, Decimal("60.00"), Decimal("40.00"))


def assert_all_costs_assigned(position: PositionDto, *partial_assignments: Decimal) -> None:
    assert len(position.funding_assignments) == len(partial_assignments)
    assert tuple(f.amount for f in position.funding_assignments) == tuple(partial_assignments)
    assert position.unassigned_costs == Decimal("0.00")

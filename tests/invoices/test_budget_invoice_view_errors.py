"""User-visible capacity errors on the invoice create/update views (test plan
seam S7 / G2): an over-capacity funding assignment must block the save and
render the service's error message inline — never a 500 — and persist nothing."""

import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.invoices import budget_query, funding_source_repository, repository
from coda.contexts.finance.dto.edit_position_dtos import FundingAssignmentDto, PositionList
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.contexts.finance.services import invoice_parser, invoice_service
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.money import Currency, Money
from tests import domainfactory, modelfactory
from tests.invoices import budget_setup


def _invoice_head(expected: Invoice) -> InvoiceHeadDto:
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
def test__create_invoice__over_capacity_assignment__blocked_with_inline_error(
    client: Client,
) -> None:
    budget = domainfactory.budget()

    creditor = CreditorId(modelfactory.creditor().pk)
    invoice = domainfactory.invoice(creditor=creditor, positions=[])

    position = domainfactory.free_position(Currency.EUR)
    invoice.positions = [position]

    # A budget that cannot cover the position's full cost.
    budget.amount = Money(position.cost.amount / 2, Currency.EUR)
    budget.id = funding_source_repository.create(budget)

    head = _invoice_head(invoice)
    position_dto = invoice_parser.position_to_dto(position)
    position_dto.funding_assignments.append(
        FundingAssignmentDto(funding_source=budget.id, amount=position.cost.amount)
    )

    response = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(head)
        | formdata.map_to_dict(PositionList(positions=[position_dto])),
    )

    assert response.status_code == 200
    assert b"exceeds its capacity" in response.content
    assert repository.first() is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_invoice__raised_assignment_beyond_capacity__blocked_with_inline_error(
    client: Client,
) -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", Currency.EUR))
    invoice_a = budget_setup.an_unsaved_invoice_with_assignment(Money("600", Currency.EUR), budget)
    invoice_a.id = invoice_service.save(invoice_a)
    budget_setup.an_invoice_with_assignment(Money("400", Currency.EUR), budget)

    # Edit: raise the position (and its assignment) to 700 — the +100 delta
    # exceeds the budget's remaining capacity (B holds the other 400).
    edited = budget_setup.an_unsaved_invoice_with_assignment(Money("700", Currency.EUR), budget)
    edited.id = invoice_a.id

    head = _invoice_head(edited)
    position_dto = invoice_parser.position_to_dto(edited.positions[0])
    position_dto.funding_assignments[0].funding_source = budget.id

    response = client.post(
        reverse("invoices:update", kwargs={"pk": invoice_a.id}),
        formdata.map_to_dict(head) | formdata.map_to_dict(PositionList(positions=[position_dto])),
    )

    assert response.status_code == 200
    assert b"exceeds its capacity" in response.content
    # Nothing persisted: the invoice's assignment stays at 600 and the
    # budget's reserved total is unchanged (600 from A + 400 from B).
    saved = repository.get_by_id(invoice_a.id)
    assignment = next(iter(saved.positions)).funding_assignments()[0]
    assert assignment.amount == Money("600", Currency.EUR)
    assert budget_query.budget_balances(budget_id).reserved == Money("1000", Currency.EUR)

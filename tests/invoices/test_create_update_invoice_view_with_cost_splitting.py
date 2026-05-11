from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.invoices import funding_source_repository, repository
from coda.contexts.finance.dto.edit_position_dtos import FundingAssignmentDto, PositionList
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
def test__invalid_split_amount__create_invoice__shows_error(client: Client) -> None:
    budget = domainfactory.budget()
    budget.id = funding_source_repository.create(budget)

    creditor = CreditorId(modelfactory.creditor().pk)
    invoice = domainfactory.invoice(creditor=creditor, positions=[])

    position = domainfactory.free_position()
    invoice.positions = [position]

    _invoice_head = invoice_head(invoice)
    position_dto = invoice_parser.position_to_dto(position)
    position_dto.funding_assignments.append(
        FundingAssignmentDto(funding_source=budget.id, amount=Decimal(position.cost.amount + 100))
    )

    response = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(_invoice_head)
        | formdata.map_to_dict(PositionList(positions=[position_dto])),
    )

    assert response.context["position_list"].positions[0].error


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_split_amount__update_invoice__shows_error(client: Client) -> None:
    budget = domainfactory.budget()
    budget.id = funding_source_repository.create(budget)
    position = domainfactory.free_position()

    creditor = CreditorId(modelfactory.creditor().pk)
    invoice = domainfactory.invoice(creditor=creditor, positions=[])
    invoice.reset_payment()
    invoice.positions = [position]
    invoice.id = repository.create(invoice)

    _invoice_head = invoice_head(invoice)
    position_dto = invoice_parser.position_to_dto(position)
    position_dto.funding_assignments.append(
        FundingAssignmentDto(
            funding_source=budget.id.pk, amount=Decimal(position.cost.amount + 100)
        )
    )

    response = client.post(
        reverse("invoices:update", kwargs={"pk": invoice.id.pk}),
        {"action": "create"}
        | formdata.map_to_dict(_invoice_head)
        | formdata.map_to_dict(PositionList(positions=[position_dto])),
    )

    assert response.context["position_list"].positions[0].error


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
        reverse("invoices:update", kwargs={"pk": expected.id.pk}),
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
        creditor=expected.creditor.pk,
        currency=expected.currency(),
        external_invoice_id=expected.external_invoice_id,
        status=expected.status,
        comment=expected.comment,
    )

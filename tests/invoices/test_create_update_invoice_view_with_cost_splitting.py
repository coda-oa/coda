from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.invoices import repository
from coda.contexts.finance.dto.edit_position_dtos import PositionList
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.contexts.finance.services import invoice_parser, invoice_service
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice
from coda.domain.money import Currency
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_invoice_with_positions_with_split_costs__saves_to_db(client: Client) -> None:
    funding_source_1 = FundingSourceId(modelfactory.funding_source("first").pk)
    funding_source_2 = FundingSourceId(modelfactory.funding_source("second").pk)
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
    funding_source_1 = FundingSourceId(modelfactory.funding_source("first").pk)
    funding_source_2 = FundingSourceId(modelfactory.funding_source("second").pk)
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

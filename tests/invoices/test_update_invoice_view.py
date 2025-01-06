import datetime
from typing import cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda.apps.contracts.services import contract_create
from coda.apps.invoices.services import invoice_create
from coda.apps.invoices.views.positions import ContractPosition, FreePosition, PublicationPosition
from coda.apps.publications.repositories import publication_repository
from coda.contract import Contract, ContractYear
from coda.invoice import CostType, CreditorId, Invoice, Position, TaxRate
from coda.money import Currency, Money
from coda.publication import JournalId, Publication, PublicationId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__goto_update_view__has_invoice_details_in_context(client: Client) -> None:
    a_publication = domainfactory.publication(JournalId(modelfactory.journal().id))
    a_publication.id = publication_repository.save(a_publication)
    _publication_position = publication_position(a_publication)

    a_contract = domainfactory.contract()
    a_contract.id = contract_create(a_contract)
    _contract_position = contract_position(a_contract)

    _free_position = free_position()

    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[_publication_position, _contract_position, _free_position],
    )

    invoice.id = invoice_create(invoice)

    response = goto_update_view(client, invoice.id)

    assert response.context["positions"] == [
        expect_publication_position(_publication_position),
        expect_contract_position(_contract_position),
        expect_free_position(_free_position),
    ]


def publication_position(a_publication: Publication) -> Position[PublicationId]:
    return Position(
        item=cast(PublicationId, a_publication.id),
        cost=Money(200, Currency.EUR),
        cost_type=CostType.Publication_Charge,
        tax_rate=TaxRate(19),
    )


def contract_position(a_contract: Contract) -> Position[ContractYear]:
    return Position(
        item=a_contract.in_first_year(),
        cost=Money(100, Currency.EUR),
        cost_type=CostType.Publication_Charge,
        tax_rate=TaxRate(19),
    )


def free_position() -> Position[str]:
    return Position(
        item="Free position",
        cost=Money(50, Currency.EUR),
        cost_type=CostType.Other,
        tax_rate=TaxRate(7),
    )


def expect_publication_position(
    publication_position: Position[PublicationId],
) -> PublicationPosition:
    publication = publication_repository.get_by_id(publication_position.item)

    return PublicationPosition(
        id=publication.id,
        title=publication.title,
        cost_amount=publication_position.cost.amount,
        tax_rate=publication_position.tax_rate,
    )


def expect_contract_position(contract_position: Position[ContractYear]) -> ContractPosition:
    contract = contract_position.item.contract

    return ContractPosition(
        id=contract.id,
        name=contract.name,
        contract_year=contract_position.item.year,
        cost_amount=contract_position.cost.amount,
        cost_type=contract_position.cost_type,
        tax_rate=contract_position.tax_rate,
    )


def expect_free_position(free_position: Position[str]) -> FreePosition:
    return FreePosition(
        description=free_position.item,
        cost_amount=free_position.cost.amount,
        cost_type=free_position.cost_type,
        tax_rate=free_position.tax_rate,
    )


def goto_update_view(client: Client, invoice_id: int) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:update", kwargs={"pk": invoice_id})))

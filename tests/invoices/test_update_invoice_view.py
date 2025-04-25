import datetime
import random
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.contracts import repository as contract_services
from coda.apps.invoices import repository
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.repository import save
from coda.apps.invoices.views.positions import ContractPosition, FreePosition, PublicationPosition
from coda.apps.publications.repositories import publication_repository
from coda.domain.contract import Contract, ContractYear
from coda.domain.invoice import (
    CostType,
    CreditorId,
    Invoice,
    InvoiceId,
    PaymentStatus,
    Position,
    TaxRate,
)
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, Publication, PublicationId
from tests import domainfactory, modelfactory
from tests.invoices.test_create_invoice_view import (
    InvalidContractYear,
    _random_funding_source,
    create_contract_position_input,
    expect_existing_contract_position,
    number_of_positions,
)
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__goto_update_view__has_invoice_head_in_form(client: Client) -> None:
    _free_position = free_position()
    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[_free_position],
        comment="A comment",
    )

    invoice.id = save(invoice)

    response = goto_update_view(client, invoice.id)

    invoice_form: InvoiceForm = response.context["form"]

    assert invoice_form.data["number"] == invoice.number
    assert invoice_form.data["creditor"] == invoice.creditor
    assert invoice_form.data["date"] == invoice.date
    assert invoice_form.data["currency"] == _free_position.cost.currency.code
    assert invoice_form.data["status"] == invoice.status.value
    assert invoice_form.data["comment"] == invoice.comment
    assert invoice_form.data["external_invoice_id"] == invoice.external_invoice_id


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__goto_update_view__has_invoice_positions_in_context(client: Client) -> None:
    a_publication = domainfactory.publication(JournalId(modelfactory.journal().id))
    a_publication.id = publication_repository.create(a_publication)
    _publication_position = publication_position(a_publication)

    a_contract = domainfactory.contract()
    a_contract.id = contract_services.create(a_contract)
    _contract_position = contract_position(a_contract)

    _free_position = free_position()

    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[_publication_position, _contract_position, _free_position],
    )

    invoice.id = save(invoice)

    response = goto_update_view(client, invoice.id)

    assert response.context["positions"] == [
        expect_publication_position(_publication_position),
        expect_contract_position(_contract_position),
        expect_free_position(_free_position),
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__saving_updated_invoice__updates_invoice(client: Client) -> None:
    creditor = modelfactory.creditor()
    first_position = domainfactory.free_position(currency=Currency.EUR)
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[first_position],
        comment="A comment",
    )

    invoice.id = save(invoice)

    second_position = domainfactory.free_position(currency=Currency.EUR)

    expected = Invoice(
        id=invoice.id,
        number="456",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[first_position, second_position],
        status=PaymentStatus.Paid,
        comment="Another comment",
        external_invoice_id="external",
    )

    post_data = (
        {
            "number": expected.number,
            "creditor": expected.creditor,
            "date": expected.date,
            "status": expected.status.value,
            "comment": expected.comment,
            "currency": expected.currency().code,
            "external_invoice_id": expected.external_invoice_id,
        }
        | number_of_positions(2)
        | expect_free_position(first_position).to_post_data(
            prefix="position-1", underscores_to_dash=True
        )
        | expect_free_position(second_position).to_post_data(
            prefix="position-2", underscores_to_dash=True
        )
    )

    response = save_invoice_view(client, invoice.id, post_data)

    actual = repository.get_by_id(invoice.id)
    assert_invoice_eq(expected, actual)
    assertRedirects(response, reverse("invoices:detail", kwargs={"pk": invoice.id}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__invalid_form__does_not_save_invoice(client: Client) -> None:
    creditor = modelfactory.creditor()
    first_position = domainfactory.free_position(currency=Currency.EUR)
    expected = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[first_position],
        comment="A comment",
    )

    expected.id = save(expected)

    post_data = {
        "number": "123",
        "creditor": CreditorId(-1),
        "date": expected.date,
        "status": expected.status.value,
        "comment": expected.comment,
        "currency": expected.currency().code,
    }

    _ = save_invoice_view(client, expected.id, post_data)

    actual = repository.get_by_id(expected.id)
    assert_invoice_eq(expected, actual)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__invalid_position__keeps_entered_position_data(client: Client) -> None:
    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.id),
        date=datetime.date.today(),
        positions=[],
    )

    invoice.id = save(invoice)

    contract = domainfactory.contract()
    contract.id = contract_services.create(contract)
    contract_year = InvalidContractYear(contract, 1)
    contract_input = create_contract_position_input(contract_year, 1)

    post_data = (
        {
            "number": invoice.number,
            "creditor": invoice.creditor,
            "date": invoice.date,
            "status": invoice.status.value,
            "comment": invoice.comment,
            "currency": invoice.currency().code,
            "external_invoice_id": invoice.external_invoice_id,
        }
        | number_of_positions(1)
        | contract_input
    )

    response = save_invoice_view(client, invoice.id, post_data)

    assert response.context["positions"] == [expect_existing_contract_position(contract_input)]


def save_invoice_view(
    client: Client, invoice_id: InvoiceId, post_data: dict[str, Any]
) -> TemplateResponse:
    print("Post data: ", post_data)
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:update", kwargs={"pk": invoice_id}), post_data),
    )


def publication_position(a_publication: Publication) -> Position[PublicationId]:
    cost_type = random.choice(list(CostType))
    return Position(
        item=cast(PublicationId, a_publication.id),
        funding_source=_random_funding_source(),
        cost=Money(200, Currency.EUR),
        cost_type=cost_type,
        tax_rate=TaxRate.from_percentage(19),
        external_position_id=f"external-publication-{a_publication.id}",
    )


def contract_position(a_contract: Contract) -> Position[ContractYear]:
    return Position(
        item=a_contract.in_first_year(),
        funding_source=_random_funding_source(),
        cost=Money(100, Currency.EUR),
        cost_type=CostType.Publication_Charge,
        tax_rate=TaxRate.from_percentage(19),
        external_position_id=f"external-contract-{a_contract.id}",
    )


def free_position() -> Position[str]:
    return Position(
        item="Free position",
        funding_source=_random_funding_source(),
        cost=Money(50, Currency.EUR),
        cost_type=CostType.Other,
        tax_rate=TaxRate.from_percentage(7),
        external_position_id="external-free",
    )


def expect_publication_position(
    publication_position: Position[PublicationId],
) -> PublicationPosition:
    publication = publication_repository.get_by_id(publication_position.item)

    return PublicationPosition(
        id=publication.id,
        title=publication.title,
        funding_source=publication_position.funding_source,
        cost_type=publication_position.cost_type,
        cost_amount=publication_position.cost.amount,
        tax_rate=publication_position.tax_rate.percentage(),
        external_position_id=publication_position.external_position_id,
    )


def expect_contract_position(contract_position: Position[ContractYear]) -> ContractPosition:
    contract = contract_position.item.contract

    return ContractPosition(
        id=contract.id,
        name=contract.name,
        year=contract_position.item.year,
        funding_source=contract_position.funding_source,
        cost_amount=contract_position.cost.amount,
        cost_type=contract_position.cost_type,
        tax_rate=contract_position.tax_rate.percentage(),
        external_position_id=contract_position.external_position_id,
    )


def expect_free_position(free_position: Position[str]) -> FreePosition:
    return FreePosition(
        description=free_position.item,
        funding_source=free_position.funding_source,
        cost_amount=free_position.cost.amount,
        cost_type=free_position.cost_type,
        tax_rate=free_position.tax_rate.percentage(),
        external_position_id=free_position.external_position_id,
    )


def goto_update_view(client: Client, invoice_id: int) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:update", kwargs={"pk": invoice_id})))

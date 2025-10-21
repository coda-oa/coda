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
from coda.apps.invoices.repository import create
from coda.apps.publications.repositories import publication_repository
from coda.contexts.finance.services import invoice_parser
from coda.domain.contract import Contract
from coda.domain.invoice import (
    ContractCostType,
    ContractItem,
    ContractPosition,
    CreditorId,
    FreeItem,
    FreePosition,
    Invoice,
    InvoiceId,
    PaymentStatus,
    PublicationPosition,
    PublicationCostType,
    PublicationItem,
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
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[_free_position],
        comment="A comment",
    )

    invoice.id = create(invoice)

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
    a_publication = domainfactory.publication(JournalId(modelfactory.journal().pk))
    a_publication.id = publication_repository.create(a_publication)
    _publication_position = publication_position(a_publication)

    a_contract = domainfactory.contract()
    a_contract.id = contract_services.create(a_contract)
    _contract_position = contract_position(a_contract)

    _free_position = free_position()

    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[_publication_position, _contract_position, _free_position],
    )

    invoice.id = create(invoice)

    response = goto_update_view(client, invoice.id)

    assert response.context["positions"] == [
        invoice_parser.position_to_dto(_publication_position),
        invoice_parser.position_to_dto(_contract_position),
        invoice_parser.position_to_dto(_free_position),
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__saving_updated_invoice__updates_invoice(client: Client) -> None:
    creditor = modelfactory.creditor()
    first_position = domainfactory.free_position(currency=Currency.EUR)
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[first_position],
        comment="A comment",
    )

    invoice.id = create(invoice)

    second_position = domainfactory.free_position(currency=Currency.EUR)

    expected = Invoice(
        id=invoice.id,
        number="456",
        creditor=CreditorId(creditor.pk),
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
        | invoice_parser.position_to_dto(first_position).to_post_data(
            prefix="position-1", underscores_to_dash=True
        )
        | invoice_parser.position_to_dto(second_position).to_post_data(
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
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[first_position],
        comment="A comment",
    )

    expected.id = create(expected)

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
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[],
    )

    invoice.id = create(invoice)

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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_vat_position__invoice_is_saved__tax_rate_of_vat_position_is_zero(
    client: Client,
) -> None:
    a_publication = domainfactory.publication(JournalId(modelfactory.journal().pk))
    a_publication.id = publication_repository.create(a_publication)
    some_position = publication_position(a_publication)
    vat_position = PublicationPosition(
        item=PublicationItem(some_position.item, cost_type=PublicationCostType.Vat),
        cost=some_position.cost,
        tax_rate=some_position.tax_rate,
        funding_source=some_position.funding_source,
        external_position_id=some_position.external_position_id,
    )

    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[vat_position],
        comment="A comment",
    )

    invoice.id = create(invoice)

    response = goto_update_view(client, invoice.id)

    assert response.context["positions"][0].tax_rate == 0


def save_invoice_view(
    client: Client, invoice_id: InvoiceId, post_data: dict[str, Any]
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:update", kwargs={"pk": invoice_id}), post_data),
    )


def publication_position(a_publication: Publication) -> PublicationPosition:
    cost_type = random.choice(list(PublicationCostType))
    return PublicationPosition(
        item=PublicationItem(cast(PublicationId, a_publication.id), cost_type=cost_type),
        funding_source=_random_funding_source(),
        cost=Money(200, Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id=f"external-publication-{a_publication.id}",
    )


def contract_position(a_contract: Contract) -> ContractPosition:
    return ContractPosition(
        item=ContractItem(a_contract.in_first_year(), cost_type=ContractCostType.Publish),
        funding_source=_random_funding_source(),
        cost=Money(100, Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id=f"external-contract-{a_contract.id}",
    )


def free_position() -> FreePosition:
    return FreePosition(
        item=FreeItem("Free position", cost_type=PublicationCostType.Other),
        funding_source=_random_funding_source(),
        cost=Money(50, Currency.EUR),
        tax_rate=TaxRate.from_percentage(7),
        external_position_id="external-free",
    )


def goto_update_view(client: Client, invoice_id: int) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:update", kwargs={"pk": invoice_id})))

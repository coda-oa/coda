import datetime
from typing import Any, cast

from django.contrib.messages import get_messages
import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda import formdata
from coda.apps.contracts import repository as contract_services
from coda.apps.invoices import repository
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.publications.repositories import publication_repository
from coda.contexts.finance.dto.edit_position_dtos import (
    PositionDto,
    ContractItemDto,
    PositionList,
)
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.contexts.finance.services import invoice_parser
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import (
    CreditorId,
    Invoice,
    InvoiceId,
    PaymentStatus,
)
from coda.domain.finance.invoice_positions import PublicationItem
from coda.domain.money import Currency
from coda.domain.publication import JournalId
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__goto_update_view__has_invoice_head_in_form(client: Client) -> None:
    _free_position = domainfactory.free_position()
    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[_free_position],
        comment="A comment",
    )

    invoice.id = repository.create(invoice)

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
def test__given_invoice__goto_update_view__has_invoice_positions_in_context___position_list(
    client: Client,
) -> None:
    a_publication = domainfactory.publication(JournalId(modelfactory.journal().pk))
    a_publication.id = publication_repository.create(a_publication)
    _publication_position = domainfactory.publication_position(a_publication.id, Currency.AFN)

    a_contract = domainfactory.contract()
    a_contract.id = contract_services.create(a_contract)
    contract_year = a_contract.in_first_year()
    _contract_position = domainfactory.contract_position(contract_year, Currency.AFN)

    _free_position = domainfactory.free_position(Currency.AFN)

    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[_publication_position, _contract_position, _free_position],
    )

    invoice.id = repository.create(invoice)

    response = goto_update_view(client, invoice.id)

    expected = PositionList(
        positions=[invoice_parser.position_to_dto(p) for p in invoice.positions]
    )
    assert response.context["position_list"] == expected


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_invoice__saving_updated_invoice__updates_invoice___position_list(
    client: Client,
) -> None:
    creditor = modelfactory.creditor()
    first_position = domainfactory.free_position(currency=Currency.EUR)
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[first_position],
        comment="A comment",
    )

    invoice.id = repository.create(invoice)

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

    position_list = PositionList(
        positions=[
            invoice_parser.position_to_dto(first_position),
            invoice_parser.position_to_dto(second_position),
        ]
    )

    post_data = {
        "number": expected.number,
        "creditor": expected.creditor,
        "date": expected.date,
        "status": expected.status.value,
        "comment": expected.comment,
        "currency": expected.currency().code,
        "external_invoice_id": expected.external_invoice_id,
    } | formdata.map_to_dict(position_list)

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

    expected.id = repository.create(expected)

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

    invoice.id = repository.create(invoice)

    contract = domainfactory.contract()
    contract.id = contract_services.create(contract)
    contract_year = PositionDto(item=ContractItemDto(id=contract.id, name=contract.name, year=1))
    position_list = PositionList(positions=[contract_year])

    post_data = {
        "number": invoice.number,
        "creditor": invoice.creditor,
        "date": invoice.date,
        "status": invoice.status.value,
        "comment": invoice.comment,
        "currency": invoice.currency().code,
        "external_invoice_id": invoice.external_invoice_id,
    } | formdata.map_to_dict(position_list)

    response = save_invoice_view(client, invoice.id, post_data)

    assert response.context["position_list"] == position_list


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_vat_position__invoice_is_saved__tax_rate_of_vat_position_is_zero(
    client: Client,
) -> None:
    a_publication = domainfactory.publication(JournalId(modelfactory.journal().pk))
    a_publication.id = publication_repository.create(a_publication)
    some_position = domainfactory.publication_position(a_publication.id)
    vat_position = invoice_positions.create(
        item=PublicationItem(a_publication.id, cost_type=PublicationCostType.Vat),
        cost=some_position.cost,
        tax_rate=some_position.tax_rate,
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

    invoice.id = repository.create(invoice)

    response = goto_update_view(client, invoice.id)

    position_list = response.context["position_list"]
    assert position_list.positions[0].tax_rate == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_unassigned_costs__save_as_paid__shows_error(client: Client) -> None:
    invoice = domainfactory.invoice(positions=[], creditor=CreditorId(modelfactory.creditor().pk))
    invoice.reset_payment()
    invoice.id = repository.create(invoice)

    invoice_head = InvoiceHeadDto(
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor,
        currency=invoice.currency(),
        status=PaymentStatus.Paid,
    )
    position = domainfactory.free_position(invoice.currency())
    position.assign_funding(None, position.cost.amount / 2)

    position_dto = invoice_parser.position_to_dto(position)
    position_list = PositionList(positions=[position_dto])

    response = save_invoice_view(
        client,
        invoice.id,
        {"action": "create"}
        | formdata.map_to_dict(invoice_head)
        | formdata.map_to_dict(position_list),
    )

    messages = get_messages(response.wsgi_request)
    error_message = list(messages).pop()
    assert error_message.message == "Invoice has unassigned costs"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_free_position__selecting_vat__returns_empty_response(client: Client) -> None:
    response = client.get(
        reverse("invoices:free_position_cost_type_options"),
        {"free-position-item-cost_type": "vat"},
    )

    assert response.content == b""  # VAT cost type should return empty response (no tax rate field)


def save_invoice_view(
    client: Client, invoice_id: InvoiceId, post_data: dict[str, Any]
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:update", kwargs={"pk": invoice_id}), post_data),
    )


def goto_update_view(client: Client, invoice_id: int) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:update", kwargs={"pk": invoice_id})))

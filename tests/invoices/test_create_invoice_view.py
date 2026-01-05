import datetime
import random
from decimal import Decimal
from typing import Any, cast

import faker
import pytest
from django.contrib.messages import get_messages
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda import formdata
from coda.apps.contracts import mapper as contract_mapper
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.invoices import repository
from coda.apps.publications.models import Publication
from coda.contexts.finance.dto.edit_position_dtos import (
    DEFAULT_TAX_RATE_PERCENTAGE,
    ContractItemDto,
    FreeItemDto,
    PositionDto,
    PositionList,
    PublicationItemDto,
    RelatedFundingRequest,
)
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.contexts.finance.services import invoice_parser
from coda.domain.contract import Contract, ContractId, ContractYear
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice import CreditorId, PaymentStatus
from coda.domain.money import Currency
from coda.domain.publication import PublicationId
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq

_faker = faker.Faker()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_publication__returns_matches_in_response(client: Client) -> None:
    fr = modelfactory.fundingrequest()
    response = search_publication(client, fr.publication.title)

    expected_context = expect_publication_search_result(fr.publication)
    assert [expected_context] == response.context["publications"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_contract__returns_matches_in_response(client: Client) -> None:
    contract = contract_mapper.as_domain_object(modelfactory.contract())
    response = client.post(reverse("invoices:contract_search"), {"contract_query": contract.name})

    expected_context = expect_contract_search_result(contract)
    assert [expected_context] == response.context["contracts"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_publication_as_position__returns_position_in_response(client: Client) -> None:
    fr = modelfactory.fundingrequest()
    publication = fr.publication

    response = add_publication_position(client, publication.id)

    expected = expect_new_publication_position(publication)
    assert expected in response.context["position_list"].positions


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_contract_as_position__returns_position_in_response(client: Client) -> None:
    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    expected = expect_new_contract_position(contract_year)

    response = add_contract_position(client, expected)

    assert expected in response.context["position_list"].positions


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_free_position__returns_position_in_response(client: Client) -> None:
    expected = expect_new_free_position()
    response = client.post(
        reverse("invoices:add_position"),
        {"action": "add-free-position"} | formdata.map_to_dict(expected, prefix="free-position"),
    )

    assert expected in response.context["position_list"].positions


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__posting_position_data__includes_positions_in_context___position_list(
    client: Client,
) -> None:
    publication = modelfactory.publication()
    publication_position = domainfactory.publication_position(PublicationId(publication.pk))

    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    contract_position = domainfactory.contract_position(contract_year)

    free_position = domainfactory.free_position()

    position_list = PositionList(
        positions=[
            invoice_parser.position_to_dto(p)
            for p in (publication_position, contract_position, free_position)
        ]
    )
    response = client.post(reverse("invoices:create"), formdata.map_to_dict(position_list))

    assert response.context["position_list"] == position_list


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__two_positions_added__removing_position__removed_from_response_context___position_list(
    client: Client,
) -> None:
    p1 = domainfactory.free_position()
    p2 = domainfactory.free_position()
    first = invoice_parser.position_to_dto(p1)
    second = invoice_parser.position_to_dto(p2)

    position_list = PositionList(positions=[first, second])
    response = client.post(
        reverse("invoices:remove_position"),
        formdata.map_to_dict(position_list) | {"remove-position": "1"},
    )

    expected = PositionList(positions=[second])
    assert response.context["position_list"] == expected


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_positions__create__saves_new_invoice__position_list(client: Client) -> None:
    publication = modelfactory.publication()
    publication_position = domainfactory.publication_position(
        PublicationId(publication.pk), currency=Currency.JPY
    )

    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    contract_position = domainfactory.contract_position(contract_year, currency=Currency.JPY)

    free_position = domainfactory.free_position(currency=Currency.JPY)

    creditor = CreditorId(modelfactory.creditor().pk)
    expected = domainfactory.invoice(
        positions=[publication_position, contract_position, free_position], creditor=creditor
    )

    position_list = PositionList(
        positions=[invoice_parser.position_to_dto(p) for p in expected.positions]
    )

    invoice_head = InvoiceHeadDto(
        number=expected.number,
        date=expected.date,
        creditor=expected.creditor,
        currency=expected.currency(),
        external_invoice_id=expected.external_invoice_id,
        status=expected.status,
        comment=expected.comment,
    )

    response = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(invoice_head)
        | formdata.map_to_dict(position_list),
    )

    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(expected, actual)
    assertRedirects(response, reverse("invoices:detail", kwargs={"pk": actual.id}))


def invoice_post_data(
    positions: list[dict[str, str]], *, status: PaymentStatus = PaymentStatus.Unpaid
) -> dict[str, str]:
    creditor = modelfactory.creditor()
    post_data = {
        "action": "create",
        "number": _faker.pystr(),
        "date": _faker.date(),
        "creditor": str(creditor.pk),
        "status": status.value,
        "currency": Currency.EUR.code,
    } | number_of_positions(len(positions))

    for position in positions:
        post_data.update(position)

    return post_data


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_position_with_invalid_contract_year__create__returns_error___position_list(
    client: Client,
) -> None:
    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_item_dto = ContractItemDto(
        id=cast(int, contract.id),
        name=contract.name,
        year=1,
    )
    contract_dto = PositionDto(item=contract_item_dto)
    position_list = PositionList(positions=[contract_dto])

    invoice_head = InvoiceHeadDto(
        number="1234",
        date=datetime.date.today(),
        creditor=CreditorId(modelfactory.creditor().pk),
        currency=Currency.JPY,
        status=PaymentStatus.Unpaid,
    )
    response = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(invoice_head)
        | formdata.map_to_dict(position_list),
    )

    expected = {
        "positions-1-error": f"Contract {contract_item_dto.name} is not active in {contract_item_dto.year}",
    }
    assert expected == response.context["errors"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_unassigned_costs__save_as_paid__shows_error(client: Client) -> None:
    position = domainfactory.free_position(Currency.EUR)
    position.assign_funding(None, position.cost.amount / 2)

    invoice_head = InvoiceHeadDto(
        number="1234",
        date=datetime.date.today(),
        creditor=CreditorId(modelfactory.creditor().pk),
        currency=Currency.JPY,
        status=PaymentStatus.Paid,
    )
    position_dto = invoice_parser.position_to_dto(position)
    position_list = PositionList(positions=[position_dto])

    response = client.post(
        reverse("invoices:create"),
        {"action": "create"}
        | formdata.map_to_dict(invoice_head)
        | formdata.map_to_dict(position_list),
    )

    messages = get_messages(response.wsgi_request)
    error_message = list(messages).pop()
    assert error_message.message == "Invoice has unassigned costs"


def search_publication(
    client: Client, title: str, other_post_data: dict[str, str] | None = None
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:pub_search"), {"q": title} | (other_post_data or {})),
    )


def add_publication_position(
    client: Client, id: int, /, other_post_data: dict[str, Any] | None = None
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:add_position"),
            {"add-publication-position": id} | (other_post_data or {}),
        ),
    )


def add_contract_position(
    client: Client,
    contract_position: PositionDto,
    /,
    other_post_data: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:add_position"),
            {"action": "add-contract-position"}
            | formdata.map_to_dict(contract_position, prefix="contract")
            | (other_post_data or {}),
        ),
    )


def number_of_positions(num: int) -> dict[str, str]:
    return {"number-of-positions": str(num)}


def _random_publication_cost_type() -> str:
    return random.choice([ct.value for ct in PublicationCostType])


def _random_tax_rate() -> str:
    return str(_faker.pyint(min_value=0, max_value=100))


def _random_cost() -> str:
    return str(_faker.pyfloat(max_value=100_000, right_digits=2, positive=True))


def expect_new_free_position() -> PositionDto:
    return PositionDto(
        item=FreeItemDto(
            description=_faker.sentence(),
            cost_type=_random_publication_cost_type(),
        ),
        cost_amount=Decimal(_random_cost()),
        tax_rate=Decimal(_random_tax_rate()),
    )


def expect_new_contract_position(contract_year: ContractYear) -> PositionDto:
    contract_id = cast(ContractId, contract_year.contract_id)
    year = contract_year.year
    contract_name = contract_year.name
    return PositionDto(
        item=ContractItemDto(
            id=contract_id, name=contract_name, year=year, cost_type=ContractCostType.Publish.value
        ),
        cost_amount=Decimal("0.00"),
        tax_rate=Decimal(DEFAULT_TAX_RATE_PERCENTAGE),
    )


def expect_new_publication_position(publication: Publication) -> PositionDto:
    ref = fundingrequest_repository.find_reference_by_publication(PublicationId(publication.pk))
    assert ref is not None
    return PositionDto(
        item=PublicationItemDto(
            id=publication.pk,
            title=publication.title,
            funding_request=RelatedFundingRequest(request_id=ref.request_id, url=ref.url),
            cost_type=PublicationCostType.Publication_Charge.value,
        ),
        cost_amount=Decimal("0.00"),
        tax_rate=Decimal(DEFAULT_TAX_RATE_PERCENTAGE),
    )


def expect_contract_search_result(contract: Contract) -> dict[str, Any]:
    return {
        "id": contract.id,
        "name": contract.name,
        "url": reverse("contracts:detail", kwargs={"pk": contract.id}),
    }


def expect_publication_search_result(publication: Publication) -> dict[str, Any]:
    pub_id = PublicationId(publication.pk)
    ref = fundingrequest_repository.find_reference_by_publication(pub_id)
    assert ref is not None
    return {
        "id": pub_id,
        "title": publication.title,
        "funding_request": ({"request_id": ref.request_id, "url": ref.url}),
    }

import datetime
import random
from typing import Any, cast

import faker
import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.invoices.services import get_by_id
from coda.apps.invoices.views.create import DEFAULT_TAX_RATE_PERCENTAGE
from coda.apps.publications.models import Publication
from coda.invoice import CostType, CreditorId, Invoice, InvoiceId, Position, TaxRate
from coda.money import Currency, Money
from coda.publication import PublicationId
from tests import modelfactory
from tests.invoices.test_invoice_services import assert_invoice_eq

_faker = faker.Faker()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_publication__returns_matches_in_response(client: Client) -> None:
    fr = modelfactory.fundingrequest()
    response = search(client, fr.publication.title)

    expected_context = expect_search_result(fr.publication)
    assert expected_context in response.context["publications"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_publication_as_position__returns_position_in_response(client: Client) -> None:
    fr = modelfactory.fundingrequest()
    publication = fr.publication

    response = add_publication_position(client, publication.id)

    expected = expect_new_publication_position(publication)
    assert expected in response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_free_position__returns_position_in_response(client: Client) -> None:
    position_data = new_free_position_data()
    response = client.post(reverse("invoices:create"), position_data)

    expected = expect_new_free_position(position_data)
    assert expected in response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__changing_publication_position_data__updates_position_in_response(client: Client) -> None:
    publication = modelfactory.publication()
    position_data = number_of_positions(1) | create_publication_position_input(publication)
    response = client.post(reverse("invoices:create"), position_data)

    expected = expect_existing_publication_position(position_data)
    assert expected in response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__changing_free_position_data__updates_position_in_response(client: Client) -> None:
    position_data = number_of_positions(1) | create_free_position_input()
    response = client.post(reverse("invoices:create"), position_data)

    expected = expect_existing_free_position(position_data)
    assert [expected] == response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_position_added__removing_position__position_removed_from_response(
    client: Client,
) -> None:
    first = modelfactory.publication()
    second = modelfactory.publication()
    position_data = (
        number_of_positions(2)
        | create_publication_position_input(first, 1)
        | create_publication_position_input(second, 2)
    )

    response = client.post(reverse("invoices:create"), position_data | {"remove-position": "1"})

    assert response.context["positions"] == [expect_existing_publication_position(position_data, 2)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_positions_added__create__saves_new_invoice(client: Client) -> None:
    creditor = modelfactory.creditor()
    first = modelfactory.publication()

    first_position_data = create_publication_position_input(first, 1)
    second_position_data = create_free_position_input(2)

    post_data = (
        {
            "action": "create",
            "number": _faker.pystr(),
            "date": _faker.date(),
            "creditor": creditor.id,
            "currency": Currency.EUR.code,
        }
        | number_of_positions(2)
        | first_position_data
        | second_position_data
    )

    response = client.post(reverse("invoices:create"), post_data)

    actual = get_by_id(InvoiceId(1))
    expected = expected_invoice(post_data)
    assert_invoice_eq(expected, actual)
    assertRedirects(response, reverse("invoices:detail", kwargs={"pk": 1}))


def expected_invoice(post_data: dict[str, str]) -> Invoice:
    return Invoice.new(
        post_data["number"],
        datetime.date.fromisoformat(post_data["date"]),
        CreditorId(int(post_data["creditor"])),
        [
            Position(
                PublicationId(int(post_data["position-1-id"])),
                Money(
                    post_data["position-1-cost"],
                    Currency[post_data["currency"]],
                ),
                CostType(post_data["position-1-cost-type"]),
                TaxRate(int(post_data["position-1-taxrate"]) / 100),
            ),
            Position(
                post_data["position-2-description"],
                Money(
                    post_data["position-2-cost"],
                    Currency[post_data["currency"]],
                ),
                CostType(post_data["position-2-cost-type"]),
                TaxRate(int(post_data["position-2-taxrate"]) / 100),
            ),
        ],
    )


def search(
    client: Client, title: str, other_post_data: dict[str, str] | None = None
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:create"), {"q": title} | (other_post_data or {})),
    )


def add_publication_position(
    client: Client, id: int, /, other_post_data: dict[str, Any] | None = None
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:create"), {"add-publication-position": id} | (other_post_data or {})
        ),
    )


def number_of_positions(num: int) -> dict[str, str]:
    return {"number-of-positions": str(num)}


def create_free_position_input(index: int = 1) -> dict[str, str]:
    return {
        f"position-{index}-type": "free",
        f"position-{index}-description": _faker.sentence(),
        f"position-{index}-cost": _random_cost(),
        f"position-{index}-taxrate": _random_tax_rate(),
        f"position-{index}-cost-type": _random_cost_type(),
    }


def create_publication_position_input(publication: Publication, index: int = 1) -> dict[str, str]:
    if hasattr(publication, "fundingrequest"):
        request_id = publication.fundingrequest.request_id
        url = publication.fundingrequest.get_absolute_url()
    else:
        request_id = ""
        url = ""

    return {
        f"position-{index}-type": "publication",
        f"position-{index}-id": str(publication.id),
        f"position-{index}-title": publication.title,
        f"position-{index}-cost": _random_cost(),
        f"position-{index}-taxrate": _random_tax_rate(),
        f"position-{index}-cost-type": _random_cost_type(),
        f"position-{index}-fundingrequest-id": request_id,
        f"position-{index}-fundingrequest-url": url,
    }


def new_free_position_data() -> dict[str, str]:
    return {
        "action": "add-free-position",
        "free-position-description": _faker.sentence(),
        "free-position-cost": _random_cost(),
        "free-position-taxrate": _random_tax_rate(),
        "free-position-cost-type": _random_cost_type(),
    }


def _random_cost_type() -> str:
    return random.choice([ct.value for ct in CostType])


def _random_tax_rate() -> str:
    return str(_faker.pyint(min_value=0, max_value=100))


def _random_cost() -> str:
    return str(_faker.pyfloat(max_value=100_000, right_digits=2, positive=True))


def expect_new_free_position(free_position_data: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "free",
        "description": free_position_data["free-position-description"],
        "cost_amount": free_position_data["free-position-cost"],
        "cost_type": free_position_data["free-position-cost-type"],
        "tax_rate": free_position_data["free-position-taxrate"],
    }


def expect_existing_free_position(position_data: dict[str, str], index: int = 1) -> dict[str, Any]:
    return {
        "type": "free",
        "description": position_data[f"position-{index}-description"],
        "cost_amount": position_data[f"position-{index}-cost"],
        "cost_type": position_data[f"position-{index}-cost-type"],
        "tax_rate": position_data[f"position-{index}-taxrate"],
    }


def expect_new_publication_position(publication: Publication) -> dict[str, Any]:
    return {
        "type": "publication",
        "id": str(publication.id),
        "title": publication.title,
        "funding_request": (
            {
                "request_id": publication.fundingrequest.request_id,
                "url": publication.fundingrequest.get_absolute_url(),
            }
            if hasattr(publication, "fundingrequest")
            else {"request_id": "", "url": ""}
        ),
        "cost_amount": str(0.00),
        "cost_type": CostType.Publication_Charge.value,
        "tax_rate": str(DEFAULT_TAX_RATE_PERCENTAGE),
    }


def expect_existing_publication_position(
    position_data: dict[str, str], i: int = 1
) -> dict[str, Any]:
    return {
        "type": "publication",
        "id": position_data[f"position-{i}-id"],
        "title": position_data[f"position-{i}-title"],
        "funding_request": {
            "request_id": position_data[f"position-{i}-fundingrequest-id"],
            "url": position_data[f"position-{i}-fundingrequest-url"],
        },
        "cost_amount": position_data[f"position-{i}-cost"],
        "cost_type": position_data[f"position-{i}-cost-type"],
        "tax_rate": position_data[f"position-{i}-taxrate"],
    }


def expect_search_result(publication: Publication) -> dict[str, Any]:
    fr = publication.fundingrequest if hasattr(publication, "fundingrequest") else None
    return {
        "id": publication.id,
        "title": publication.title,
        "funding_request": (
            {"request_id": fr.request_id, "url": fr.get_absolute_url()}
            if fr
            else {"request_id": "", "url": ""}
        ),
    }

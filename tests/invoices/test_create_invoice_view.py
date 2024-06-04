import datetime
from typing import Any, cast

import faker
import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.invoices.services import get_by_id
from coda.apps.invoices.views import DEFAULT_TAX_RATE_PERCENTAGE
from coda.apps.publications.models import Publication
from coda.invoice import CreditorId, Invoice, InvoiceId, Position, TaxRate
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
def test__creditor_selected__searching_for_publication__returns_only_publications_from_creditor(
    client: Client,
) -> None:
    match = modelfactory.publication()
    pub_from_other_publisher = modelfactory.publication(title=match.title)

    creditor = match.journal.publisher.id
    response = search(client, match.title, {"creditor": str(creditor)})

    expected_search_result = expect_search_result(match)
    excluded_search_result = expect_search_result(pub_from_other_publisher)
    assert expected_search_result in response.context["publications"]
    assert excluded_search_result not in response.context["publications"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_publication_as_position__returns_position_in_response(client: Client) -> None:
    fr = modelfactory.fundingrequest()
    publication = fr.publication

    response = add_position(client, publication.id)

    expected = expect_new_position_data(publication)
    assert expected in response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__changing_position_data__updates_position_in_response(client: Client) -> None:
    publication = modelfactory.publication()
    position_data = number_of_positions(1) | create_position_input(publication)
    response = client.post(reverse("invoices:create"), position_data)

    expected = expect_existing_position_data(position_data)
    assert expected in response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_position_added__adding_another_position__second_position_has_number_2(
    client: Client,
) -> None:
    first = modelfactory.publication()
    second = modelfactory.publication()

    first_position_data = create_position_input(first)
    response = add_position(
        client,
        second.id,
        other_post_data=(number_of_positions(1) | first_position_data),
    )

    first_expected = expect_existing_position_data(first_position_data, 1)
    second_expected = expect_new_position_data(second, 2)
    assert response.context["positions"] == [first_expected, second_expected]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_position_added__removing_position__position_removed_from_response(
    client: Client,
) -> None:
    first = modelfactory.publication()
    second = modelfactory.publication()
    position_data = (
        number_of_positions(2) | create_position_input(first, 1) | create_position_input(second, 2)
    )

    response = client.post(reverse("invoices:create"), position_data | {"remove-position": "1"})

    assert response.context["positions"] == [expect_existing_position_data(position_data, 2)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_positions_added__create__saves_new_invoice(client: Client) -> None:
    first = modelfactory.publication()
    second = modelfactory.publication()

    first_position_data = create_position_input(first, 1)
    second_position_data = create_position_input(second, 2)

    post_data = (
        {
            "action": "create",
            "number": _faker.pystr(),
            "date": _faker.date(),
            "creditor": first.journal.publisher.id,
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
                    Currency[post_data["position-1-currency"]],
                ),
                TaxRate(int(post_data["position-1-taxrate"]) / 100),
            ),
            Position(
                PublicationId(int(post_data["position-2-id"])),
                Money(
                    post_data["position-2-cost"],
                    Currency[post_data["position-2-currency"]],
                ),
                TaxRate(int(post_data["position-2-taxrate"]) / 100),
            ),
        ],
    )


def expect_existing_position_data(position_data: dict[str, str], i: int = 1) -> dict[str, Any]:
    return {
        "number": position_data[f"position-{i}-number"],
        "id": int(position_data[f"position-{i}-id"]),
        "title": position_data[f"position-{i}-title"],
        "funding_request": {
            "request_id": position_data[f"position-{i}-fundingrequest-id"],
            "url": position_data[f"position-{i}-fundingrequest-url"],
        },
        "cost_amount": float(position_data[f"position-{i}-cost"]),
        "cost_currency": position_data[f"position-{i}-currency"],
        "tax_rate": position_data[f"position-{i}-taxrate"],
        "description": "",
    }


def search(
    client: Client, title: str, other_post_data: dict[str, str] | None = None
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:create"), {"q": title} | (other_post_data or {})),
    )


def add_position(
    client: Client, id: int, /, other_post_data: dict[str, Any] | None = None
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(reverse("invoices:create"), {"add_position": id} | (other_post_data or {})),
    )


def number_of_positions(num: int) -> dict[str, str]:
    return {"number-of-positions": str(num)}


def create_position_input(publication: Publication, index: int = 1) -> dict[str, str]:
    if hasattr(publication, "fundingrequest"):
        request_id = publication.fundingrequest.request_id
        url = publication.fundingrequest.get_absolute_url()
    else:
        request_id = ""
        url = ""
    return {
        f"position-{index}-number": str(index),
        f"position-{index}-id": str(publication.id),
        f"position-{index}-title": publication.title,
        f"position-{index}-cost": str(
            _faker.pyfloat(max_value=100_000, right_digits=2, positive=True)
        ),
        f"position-{index}-currency": "EUR",
        f"position-{index}-taxrate": str(_faker.pyint(min_value=0, max_value=100)),
        f"position-{index}-fundingrequest-id": request_id,
        f"position-{index}-fundingrequest-url": url,
    }


def expect_new_position_data(publication: Publication, number: int = 1) -> dict[str, Any]:
    return {
        "number": str(number),
        "id": publication.id,
        "title": publication.title,
        "funding_request": (
            {
                "request_id": publication.fundingrequest.request_id,
                "url": publication.fundingrequest.get_absolute_url(),
            }
            if hasattr(publication, "fundingrequest")
            else {"request_id": "", "url": ""}
        ),
        "cost_amount": 0.00,
        "cost_currency": "EUR",
        "tax_rate": DEFAULT_TAX_RATE_PERCENTAGE,
        "description": "",
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

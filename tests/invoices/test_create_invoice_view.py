import datetime
import random
from dataclasses import dataclass
from typing import Any, Protocol, cast

import faker
import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.contracts import services as contract_services
from coda.apps.invoices.repository import get_by_id
from coda.apps.invoices.views.positions import (
    DEFAULT_TAX_RATE_PERCENTAGE,
    ContractPosition,
    FreePosition,
    PublicationPosition,
    RelatedFundingRequest,
)
from coda.apps.publications.models import Publication
from coda.contract import Contract, ContractId
from coda.invoice import CostType, CreditorId, Invoice, InvoiceId, PaymentStatus, Position, TaxRate
from coda.money import Currency, Money
from coda.publication import PublicationId
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
    contract = contract_services.as_domain_object(modelfactory.contract())
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
    assert [expected] == response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_contract_as_position__returns_position_in_response(client: Client) -> None:
    contract = contract_services.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)

    response = add_contract_position(client, contract_year)

    expected = expect_new_contract_position(
        contract_year.contract_id, contract_year.year, contract_year.name
    )
    assert [expected] == response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_free_position__returns_position_in_response(client: Client) -> None:
    position_data = new_free_position_data()
    response = client.post(reverse("invoices:add_position"), position_data)

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
def test__changing_contract_position_data__updates_position_in_response(client: Client) -> None:
    contract = contract_services.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    position_data = number_of_positions(1) | create_contract_position_input(contract_year)
    response = client.post(reverse("invoices:create"), position_data)

    expected = expect_existing_contract_position(position_data)
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

    response = client.post(
        reverse("invoices:remove_position"), position_data | {"remove-position": "1"}
    )

    assert response.context["positions"] == [expect_existing_publication_position(position_data, 2)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_positions_added__create__saves_new_invoice(client: Client) -> None:
    creditor = modelfactory.creditor()
    publication = modelfactory.publication()
    contract = contract_services.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)

    first_position_data = create_publication_position_input(publication, 1)
    second_position_data = create_free_position_input(2)
    third_position_data = create_contract_position_input(contract_year, 3)

    post_data = (
        {
            "action": "create",
            "number": _faker.pystr(),
            "date": _faker.date(),
            "creditor": str(creditor.id),
            "status": PaymentStatus.Unpaid.value,
            "currency": Currency.EUR.code,
        }
        | number_of_positions(3)
        | first_position_data
        | second_position_data
        | third_position_data
    )

    response = client.post(reverse("invoices:create"), post_data)

    actual = get_by_id(InvoiceId(1))
    expected = expected_invoice(post_data)
    assert_invoice_eq(expected, actual)
    assertRedirects(response, reverse("invoices:detail", kwargs={"pk": 1}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_position_with_invalid_contract_year__create__returns_error(client: Client) -> None:
    creditor = modelfactory.creditor()
    contract = contract_services.as_domain_object(modelfactory.contract())
    contract_year = InvalidContractYear(contract, 1)

    first_position_data = create_contract_position_input(contract_year, 1)

    post_data = (
        {
            "action": "create",
            "number": _faker.pystr(),
            "date": _faker.date(),
            "creditor": str(creditor.id),
            "status": PaymentStatus.Unpaid.value,
            "currency": Currency.EUR.code,
        }
        | number_of_positions(1)
        | first_position_data
    )

    response = client.post(reverse("invoices:create"), post_data)

    expected = {
        "position-1-error": f"Contract is not active in {contract_year.year}",
    }
    assert expected == response.context["errors"]


def expected_invoice(post_data: dict[str, str]) -> Invoice:
    contract = contract_services.get_by_id(ContractId(int(post_data["position-3-id"])))
    contract_year = contract.in_year(int(post_data["position-3-contract-year"]))
    return Invoice.new(
        post_data["number"],
        datetime.date.fromisoformat(post_data["date"]),
        CreditorId(int(post_data["creditor"])),
        [
            Position(
                PublicationId(int(post_data["position-1-id"])),
                Money(
                    post_data["position-1-cost-amount"],
                    Currency[post_data["currency"]],
                ),
                CostType(post_data["position-1-cost-type"]),
                TaxRate(int(post_data["position-1-tax-rate"]) / 100),
            ),
            Position(
                post_data["position-2-description"],
                Money(
                    post_data["position-2-cost-amount"],
                    Currency[post_data["currency"]],
                ),
                CostType(post_data["position-2-cost-type"]),
                TaxRate(int(post_data["position-2-tax-rate"]) / 100),
            ),
            Position(
                contract_year,
                Money(
                    post_data["position-3-cost-amount"],
                    Currency[post_data["currency"]],
                ),
                CostType(post_data["position-3-cost-type"]),
                TaxRate(int(post_data["position-3-tax-rate"]) / 100),
            ),
        ],
    )


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
    contract_year: "ContractYearLike",
    /,
    other_post_data: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:add_position"),
            new_contract_position_data(contract_year) | (other_post_data or {}),
        ),
    )


def new_contract_position_data(contract_year: "ContractYearLike") -> dict[str, str]:
    contract = contract_year.contract
    year = contract_year.year
    return {
        "action": "add-contract-position",
        "contract-id": str(contract.id),
        "contract-year": str(year),
        "contract-name": contract.name,
    }


def number_of_positions(num: int) -> dict[str, str]:
    return {"number-of-positions": str(num)}


def create_free_position_input(index: int = 1) -> dict[str, str]:
    return {
        f"position-{index}-type": "free",
        f"position-{index}-description": _faker.sentence(),
        f"position-{index}-cost-amount": _random_cost(),
        f"position-{index}-tax-rate": _random_tax_rate(),
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
        f"position-{index}-cost-amount": _random_cost(),
        f"position-{index}-tax-rate": _random_tax_rate(),
        f"position-{index}-cost-type": _random_cost_type(),
        f"position-{index}-fundingrequest-id": request_id,
        f"position-{index}-fundingrequest-url": url,
    }


def create_contract_position_input(contract: "ContractYearLike", index: int = 1) -> dict[str, str]:
    return {
        f"position-{index}-type": "contract",
        f"position-{index}-id": str(contract.contract.id),
        f"position-{index}-contract-year": str(contract.year),
        f"position-{index}-name": contract.name,
        f"position-{index}-cost-amount": _random_cost(),
        f"position-{index}-tax-rate": _random_tax_rate(),
        f"position-{index}-cost-type": _random_cost_type(),
    }


def new_free_position_data() -> dict[str, str]:
    return {
        "action": "add-free-position",
        "free-position-description": _faker.sentence(),
        "free-position-cost-amount": _random_cost(),
        "free-position-tax-rate": _random_tax_rate(),
        "free-position-cost-type": _random_cost_type(),
    }


def _random_cost_type() -> str:
    return random.choice([ct.value for ct in CostType])


def _random_tax_rate() -> str:
    return str(_faker.pyint(min_value=0, max_value=100))


def _random_cost() -> str:
    return str(_faker.pyfloat(max_value=100_000, right_digits=2, positive=True))


def expect_new_free_position(free_position_data: dict[str, str]) -> FreePosition:
    return FreePosition(
        description=free_position_data["free-position-description"],
        cost_amount=free_position_data["free-position-cost-amount"],
        cost_type=free_position_data["free-position-cost-type"],
        tax_rate=free_position_data["free-position-tax-rate"],
    )


def expect_new_contract_position(
    contract_id: ContractId | None, year: int, contract_name: str
) -> ContractPosition:
    return ContractPosition(
        id=contract_id,
        name=contract_name,
        contract_year=year,
        cost_amount="0.00",
        cost_type=CostType.Publication_Charge.value,
        tax_rate=str(DEFAULT_TAX_RATE_PERCENTAGE),
    )


def expect_existing_free_position(position_data: dict[str, str], index: int = 1) -> FreePosition:
    return FreePosition(
        description=position_data[f"position-{index}-description"],
        cost_amount=position_data[f"position-{index}-cost-amount"],
        cost_type=position_data[f"position-{index}-cost-type"],
        tax_rate=position_data[f"position-{index}-tax-rate"],
    )


def expect_new_publication_position(publication: Publication) -> PublicationPosition:
    return PublicationPosition(
        id=publication.id,
        title=publication.title,
        funding_request=(
            RelatedFundingRequest(
                request_id=publication.fundingrequest.request_id,
                url=publication.fundingrequest.get_absolute_url(),
            )
            if hasattr(publication, "fundingrequest")
            else RelatedFundingRequest()
        ),
        cost_amount="0.00",
        cost_type=CostType.Publication_Charge.value,
        tax_rate=str(DEFAULT_TAX_RATE_PERCENTAGE),
    )


def expect_existing_publication_position(
    position_data: dict[str, str], i: int = 1
) -> PublicationPosition:
    return PublicationPosition(
        id=int(position_data[f"position-{i}-id"]),
        title=position_data[f"position-{i}-title"],
        funding_request=RelatedFundingRequest(
            request_id=position_data[f"position-{i}-fundingrequest-id"],
            url=position_data[f"position-{i}-fundingrequest-url"],
        ),
        cost_amount=position_data[f"position-{i}-cost-amount"],
        cost_type=position_data[f"position-{i}-cost-type"],
        tax_rate=position_data[f"position-{i}-tax-rate"],
    )


def expect_existing_contract_position(
    position_data: dict[str, str], i: int = 1
) -> ContractPosition:
    return ContractPosition(
        id=int(position_data[f"position-{i}-id"]),
        name=position_data[f"position-{i}-name"],
        contract_year=int(position_data[f"position-{i}-contract-year"]),
        cost_amount=position_data[f"position-{i}-cost-amount"],
        cost_type=position_data[f"position-{i}-cost-type"],
        tax_rate=position_data[f"position-{i}-tax-rate"],
    )


def expect_contract_search_result(contract: Contract) -> dict[str, Any]:
    return {
        "id": contract.id,
        "name": contract.name,
        "url": reverse("contracts:detail", kwargs={"pk": contract.id}),
    }


def expect_publication_search_result(publication: Publication) -> dict[str, Any]:
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


class ContractYearLike(Protocol):
    @property
    def contract(self) -> Contract:
        ...

    @property
    def contract_id(self) -> ContractId | None:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def year(self) -> int:
        ...


@dataclass
class InvalidContractYear:
    contract: Contract
    year: int

    @property
    def contract_id(self) -> ContractId | None:
        return self.contract.id

    @property
    def name(self) -> str:
        return self.contract.name

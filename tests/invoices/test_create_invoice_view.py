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

from coda.apps.contracts import repository as contract_services
from coda.apps.contracts import mapper as contract_mapper
from coda.apps.invoices import repository
from coda.apps.invoices.models import FundingSource
from coda.contexts.finance.dto.edit_position_dtos import (
    DEFAULT_TAX_RATE_PERCENTAGE,
    ContractPositionDto,
    FreePositionDto,
    PublicationPositionDto,
    RelatedFundingRequest,
)
from coda.apps.publications.models import Publication
from coda.apps.publications.services import publications
from coda.domain.contract import Contract, ContractId
from coda.domain.invoice import (
    ContractCostType,
    ContractItem,
    ContractPosition,
    CreditorId,
    FreeItem,
    FreePosition,
    FundingSourceId,
    Invoice,
    PaymentStatus,
    PublicationPosition,
    PublicationCostType,
    PublicationItem,
    TaxRate,
)
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import (
    PublicationPayments,
)
from tests import domainfactory, modelfactory
from tests.invoices.payment_assertions import (
    CreatePaymentsAssertion,
    new_invoice_paid_assertion,
    new_invoice_received_assertion,
)
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
    assert [expected] == response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_contract_as_position__returns_position_in_response(client: Client) -> None:
    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    expected = expect_new_contract_position(contract_year)

    response = add_contract_position(client, expected)

    assert [expected] == response.context["positions"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_free_position__returns_position_in_response(client: Client) -> None:
    expected = expect_new_free_position()
    response = client.post(
        reverse("invoices:add_position"),
        {"action": "add-free-position"}
        | expected.to_post_data(prefix="free-position", underscores_to_dash=True),
    )

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
    contract = contract_mapper.as_domain_object(modelfactory.contract())
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
    publication = modelfactory.publication()
    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)

    first_position_data = create_publication_position_input(publication, 1)
    second_position_data = create_free_position_input(2)
    third_position_data = create_contract_position_input(contract_year, 3)

    post_data = invoice_post_data([first_position_data, second_position_data, third_position_data])
    response = client.post(reverse("invoices:create"), post_data)

    actual = repository.first()
    assert actual is not None
    expected = expected_invoice(post_data)
    assert_invoice_eq(expected, actual)
    assertRedirects(response, reverse("invoices:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize(
    ["invoice_status", "get_assertion_for_invoice"],
    [
        (PaymentStatus.Paid, new_invoice_paid_assertion),
        (PaymentStatus.Unpaid, new_invoice_received_assertion),
    ],
)
def test__given_publication_added__create__publication_has_invoice_received(
    client: Client,
    invoice_status: PaymentStatus,
    get_assertion_for_invoice: CreatePaymentsAssertion,
) -> None:
    publication = modelfactory.publication()

    post_data = invoice_post_data(
        [create_publication_position_input(publication)], status=invoice_status
    )
    client.post(reverse("invoices:create"), post_data)

    actual = repository.first()
    assert actual is not None
    assert_payment_status = get_assertion_for_invoice(actual)

    actual_status = publications.get_payment_status(PublicationId(publication.id))
    assert isinstance(actual_status, PublicationPayments)
    assert_payment_status(actual_status)


def invoice_post_data(
    positions: list[dict[str, str]], *, status: PaymentStatus = PaymentStatus.Unpaid
) -> dict[str, str]:
    creditor = modelfactory.creditor()
    post_data = {
        "action": "create",
        "number": _faker.pystr(),
        "date": _faker.date(),
        "creditor": str(creditor.id),
        "status": status.value,
        "currency": Currency.EUR.code,
    } | number_of_positions(len(positions))

    for position in positions:
        post_data.update(position)

    return post_data


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_position_with_invalid_contract_year__create__returns_error(client: Client) -> None:
    contract = contract_mapper.as_domain_object(modelfactory.contract())
    contract_year = InvalidContractYear(contract, 1)

    first_position_data = create_contract_position_input(contract_year, 1)

    post_data = invoice_post_data([first_position_data])
    response = client.post(reverse("invoices:create"), post_data)

    expected = {
        "position-1-error": f"Contract {contract.name} is not active in {contract_year.year}",
    }
    assert expected == response.context["errors"]


def expected_invoice(post_data: dict[str, str]) -> Invoice:
    contract = contract_services.get_by_id(ContractId(int(post_data["position-3-id"])))
    contract_year = contract.in_year(int(post_data["position-3-year"]))
    return Invoice.new(
        post_data["number"],
        datetime.date.fromisoformat(post_data["date"]),
        CreditorId(int(post_data["creditor"])),
        [
            PublicationPosition(
                item=PublicationItem(
                    PublicationId(int(post_data["position-1-id"])),
                    cost_type=PublicationCostType(post_data["position-1-cost-type"]),
                ),
                cost=Money(
                    post_data["position-1-cost-amount"],
                    Currency[post_data["currency"]],
                ),
                tax_rate=TaxRate(int(post_data["position-1-tax-rate"]) / 100),
                funding_source=FundingSourceId(int(post_data["position-1-funding-source"])),
                external_position_id=post_data["position-1-external-position-id"],
            ),
            FreePosition(
                item=FreeItem(
                    post_data["position-2-description"],
                    cost_type=PublicationCostType(post_data["position-2-cost-type"]),
                ),
                cost=Money(
                    post_data["position-2-cost-amount"],
                    Currency[post_data["currency"]],
                ),
                tax_rate=TaxRate(int(post_data["position-2-tax-rate"]) / 100),
                funding_source=FundingSourceId(int(post_data["position-2-funding-source"])),
                external_position_id=post_data["position-2-external-position-id"],
            ),
            ContractPosition(
                item=ContractItem(
                    contract_year,
                    cost_type=ContractCostType(post_data["position-3-cost-type"]),
                ),
                cost=Money(
                    post_data["position-3-cost-amount"],
                    Currency[post_data["currency"]],
                ),
                tax_rate=TaxRate(int(post_data["position-3-tax-rate"]) / 100),
                funding_source=FundingSourceId(int(post_data["position-3-funding-source"])),
                external_position_id=post_data["position-3-external-position-id"],
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
    contract_position: ContractPositionDto,
    /,
    other_post_data: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(
        TemplateResponse,
        client.post(
            reverse("invoices:add_position"),
            {"action": "add-contract-position"}
            | contract_position.to_post_data(prefix="contract")
            | (other_post_data or {}),
        ),
    )


def number_of_positions(num: int) -> dict[str, str]:
    return {"number-of-positions": str(num)}


def create_free_position_input(index: int = 1) -> dict[str, str]:
    return {
        f"position-{index}-type": "free",
        f"position-{index}-description": _faker.sentence(),
        f"position-{index}-funding-source": str(_random_funding_source()),
        f"position-{index}-cost-amount": _random_cost(),
        f"position-{index}-tax-rate": _random_tax_rate(),
        f"position-{index}-cost-type": _random_publication_cost_type(),
        f"position-{index}-external-position-id": str(_faker.uuid4()),
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
        f"position-{index}-cost-type": _random_publication_cost_type(),
        f"position-{index}-funding-source": str(_random_funding_source()),
        f"position-{index}-fundingrequest-id": request_id,
        f"position-{index}-fundingrequest-url": url,
        f"position-{index}-external-position-id": str(_faker.uuid4()),
    }


def create_contract_position_input(contract: "ContractYearLike", index: int = 1) -> dict[str, str]:
    return {
        f"position-{index}-type": "contract",
        f"position-{index}-id": str(contract.contract.id),
        f"position-{index}-year": str(contract.year),
        f"position-{index}-name": contract.name,
        f"position-{index}-funding-source": str(_random_funding_source()),
        f"position-{index}-cost-amount": _random_cost(),
        f"position-{index}-tax-rate": _random_tax_rate(),
        f"position-{index}-cost-type": _random_contract_cost_type(),
        f"position-{index}-external-position-id": str(_faker.uuid4()),
    }


def _random_publication_cost_type() -> str:
    return random.choice([ct.value for ct in PublicationCostType])


def _random_contract_cost_type() -> str:
    return random.choice([ct.value for ct in ContractCostType])


def _random_tax_rate() -> str:
    return str(_faker.pyint(min_value=0, max_value=100))


def _random_cost() -> str:
    return str(_faker.pyfloat(max_value=100_000, right_digits=2, positive=True))


def _random_funding_source() -> FundingSourceId:
    fs = FundingSource.objects.create(name=_faker.company())
    return FundingSourceId(fs.id)


def expect_new_free_position() -> FreePositionDto:
    return FreePositionDto(
        description=_faker.sentence(),
        cost_amount=_random_cost(),
        cost_type=_random_publication_cost_type(),
        tax_rate=_random_tax_rate(),
    )


def expect_new_contract_position(contract_year: "ContractYearLike") -> ContractPositionDto:
    contract_id = contract_year.contract_id
    year = contract_year.year
    contract_name = contract_year.name
    return ContractPositionDto(
        id=contract_id,
        name=contract_name,
        year=year,
        cost_amount="0.00",
        cost_type=ContractCostType.Publish.value,
        tax_rate=str(DEFAULT_TAX_RATE_PERCENTAGE),
    )


def expect_existing_free_position(position_data: dict[str, str], index: int = 1) -> FreePositionDto:
    return FreePositionDto(
        description=position_data[f"position-{index}-description"],
        funding_source=position_data[f"position-{index}-funding-source"],
        cost_amount=position_data[f"position-{index}-cost-amount"],
        cost_type=position_data[f"position-{index}-cost-type"],
        tax_rate=position_data[f"position-{index}-tax-rate"],
        external_position_id=position_data[f"position-{index}-external-position-id"],
    )


def expect_new_publication_position(publication: Publication) -> PublicationPositionDto:
    return PublicationPositionDto(
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
        cost_type=PublicationCostType.Publication_Charge.value,
        tax_rate=str(DEFAULT_TAX_RATE_PERCENTAGE),
    )


def expect_existing_publication_position(
    position_data: dict[str, str], i: int = 1
) -> PublicationPositionDto:
    return PublicationPositionDto(
        id=int(position_data[f"position-{i}-id"]),
        title=position_data[f"position-{i}-title"],
        funding_request=RelatedFundingRequest(
            request_id=position_data[f"position-{i}-fundingrequest-id"],
            url=position_data[f"position-{i}-fundingrequest-url"],
        ),
        funding_source=position_data[f"position-{i}-funding-source"],
        cost_amount=position_data[f"position-{i}-cost-amount"],
        cost_type=position_data[f"position-{i}-cost-type"],
        tax_rate=position_data[f"position-{i}-tax-rate"],
        external_position_id=position_data[f"position-{i}-external-position-id"],
    )


def expect_existing_contract_position(
    position_data: dict[str, str], i: int = 1
) -> ContractPositionDto:
    return ContractPositionDto(
        id=int(position_data[f"position-{i}-id"]),
        name=position_data[f"position-{i}-name"],
        year=int(position_data[f"position-{i}-year"]),
        funding_source=position_data[f"position-{i}-funding-source"],
        cost_amount=position_data[f"position-{i}-cost-amount"],
        cost_type=position_data[f"position-{i}-cost-type"],
        tax_rate=position_data[f"position-{i}-tax-rate"],
        external_position_id=position_data[f"position-{i}-external-position-id"],
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

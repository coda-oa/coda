from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from typing import cast

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.invoices import funding_source_repository
from coda.apps.invoices import invoice_query as iq
from coda.apps.publications.dto import PublicationDto
from coda.contexts.finance.services import invoice_service
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.domain.contract import Contract, ContractId
from coda.domain.date import DateRange
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice, InvoiceId
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Currency
from coda.domain.publication.publication import JournalId
from tests import domainfactory, modelfactory


@dataclass
class MatchingQueryConfig:
    matching_invoice: Invoice
    creditor_name: str
    query_str: str = "the query"


def list_item_from_invoice(invoice: Invoice, creditor_name: str) -> InvoiceListItem:
    invoice_id = cast(InvoiceId, invoice.id)
    return InvoiceListItem(
        id=invoice_id,
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor,
        creditor_name=creditor_name,
        status=invoice.status,
        currency=invoice.currency(),
        external_invoice_id=invoice.external_invoice_id,
        net=invoice.net(),
        tax=invoice.tax(),
        total=invoice.total(),
        comment=invoice.comment,
        conversions=invoice.conversions(),
        url=reverse("invoices:detail", kwargs={"pk": invoice_id}),
        has_invalid_contract_years=False,
    )


def invoice_matching_number() -> MatchingQueryConfig:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.id = invoice_service.save(invoice)
    return MatchingQueryConfig(invoice, creditor.name, query_str=invoice.number)


def invoice_matching_creditor() -> MatchingQueryConfig:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.id = invoice_service.save(invoice)
    return MatchingQueryConfig(invoice, creditor.name, query_str=creditor.name)


def invoice_matching_request_id(creditor_name: str = "") -> MatchingQueryConfig:
    creditor = modelfactory.creditor(name=creditor_name)
    creditor_id = CreditorId(creditor.pk)

    journal = JournalId(modelfactory.journal().pk)
    request = domainfactory.fundingrequest(journal_id=journal)
    request.id = fundingrequests.create_fundingrequest(
        CreateFundingRequestDto(
            publication=PublicationDto.from_publication(request.publication),
            payment=PaymentDto.from_payment(request.estimated_cost),
            extra_information=ExtraInformationDto(),
        )
    )
    saved_request = fundingrequest_repository.get_article_request(request.id)

    position = domainfactory.publication_position(saved_request.publication.id)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])
    invoice.id = invoice_service.save(invoice)
    return MatchingQueryConfig(invoice, creditor.name, query_str=str(saved_request.request_id))


def invoice_matching_external_invoice_id() -> MatchingQueryConfig:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.id = invoice_service.save(invoice)
    return MatchingQueryConfig(invoice, creditor.name, query_str=invoice.external_invoice_id)


def create_budget() -> FundingSourceId:
    return funding_source_repository.create(domainfactory.budget())


def create_contract_with_period(period: DateRange) -> Contract:
    contract = domainfactory.contract(period=period)
    contract.id = contract_repository.create(contract)
    return contract


def create_non_matching_invoice() -> Invoice:
    no_match_creditor = modelfactory.creditor(name="NO_MATCH")
    non_matching = domainfactory.invoice(creditor=CreditorId(no_match_creditor.pk), positions=())
    non_matching.number = "NO_MATCH"
    non_matching.id = invoice_service.save(non_matching)
    return non_matching


@pytest.mark.django_db
@pytest.mark.parametrize(
    "create_query_config",
    [
        invoice_matching_number,
        invoice_matching_creditor,
        invoice_matching_request_id,
        invoice_matching_external_invoice_id,
    ],
)
def test__searching_by_generic_criterion_finds_matching_invoices(
    create_query_config: Callable[[], MatchingQueryConfig],
) -> None:
    matching_query = create_query_config()
    create_non_matching_invoice()

    actual = iq.search_to_list_items(iq.GenericSearchCriterion(matching_query.query_str))

    assert actual == [
        list_item_from_invoice(matching_query.matching_invoice, matching_query.creditor_name)
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ["apply_matching_status", "apply_non_matching_status"],
    [
        [lambda i: i.pay(), lambda i: i.reset_payment()],
        [lambda i: i.reset_payment(), lambda i: i.pay()],
        [lambda i: i.reject(), lambda i: i.pay()],
    ],
)
def test__searching_by_payment_status_finds_matching_invoices(
    apply_matching_status: Callable[[Invoice], None],
    apply_non_matching_status: Callable[[Invoice], None],
) -> None:
    creditor = modelfactory.creditor()
    matching_invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=())
    apply_matching_status(matching_invoice)
    matching_invoice.id = invoice_service.save(matching_invoice)

    non_matching_invoice = create_non_matching_invoice()
    apply_non_matching_status(non_matching_invoice)
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.PaymentStatusCriterion(matching_invoice.status))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_date_range_finds_matching_invoices() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    matching_invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    matching_invoice.date = date(2024, 6, 15)
    matching_invoice.id = invoice_service.save(matching_invoice)

    non_matching_invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    non_matching_invoice.date = date(2023, 1, 1)
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    date_range = DateRange(start=date(2024, 1, 1), end=date(2024, 12, 31))

    actual = iq.search_to_list_items(iq.DateRangeCriterion(date_range))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_funding_source_finds_matching_invoices() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    matching_budget_id = create_budget()

    non_matching_budget_id = create_budget()

    matching_position = domainfactory.free_position()
    matching_position.assign_funding(
        Budget(matching_budget_id, "matching"), matching_position.cost.amount
    )

    matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[matching_position],
    )
    matching_invoice.id = invoice_service.save(matching_invoice)

    non_matching_position = domainfactory.free_position()
    non_matching_position.assign_funding(
        Budget(non_matching_budget_id, "non-matching"), non_matching_position.cost.amount
    )

    non_matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[non_matching_position],
    )
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.FundingSourceCriterion(matching_budget_id))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_missing_external_id__finds_invoices_without_external_id() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    matching_invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    matching_invoice.external_invoice_id = ""
    matching_invoice.id = invoice_service.save(matching_invoice)

    non_matching_invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    non_matching_invoice.external_invoice_id = "EXT-456"
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.MissingExternalIdCriterion())

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_contract__finds_invoices_with_matching_contract() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    matching_contract = create_contract_with_period(DateRange.year(2024))
    matching_position = domainfactory.contract_position(
        domainfactory.contract_year(matching_contract)
    )

    matching_invoice = domainfactory.invoice(creditor=creditor_id, positions=[matching_position])
    matching_invoice.id = invoice_service.save(matching_invoice)

    other_contract = create_contract_with_period(DateRange.year(2023))
    other_position = domainfactory.contract_position(domainfactory.contract_year(other_contract))

    non_matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[other_position],
    )
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.ContractCriterion(cast(ContractId, matching_contract.id)))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_contract_year__finds_invoices_with_matching_contract_year() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    matching_contract = create_contract_with_period(DateRange.year(2024))
    contract_year = domainfactory.contract_year(matching_contract)
    matching_position = domainfactory.contract_position(contract_year)

    matching_invoice = domainfactory.invoice(creditor=creditor_id, positions=[matching_position])
    matching_invoice.id = invoice_service.save(matching_invoice)

    other_contract = create_contract_with_period(DateRange.year(2023))
    other_position = domainfactory.contract_position(domainfactory.contract_year(other_contract))

    non_matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[other_position],
    )
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.ContractYearCriterion(contract_year.year))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_has_errors__finds_invoices_with_invalid_contract_years() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    matching_contract = domainfactory.contract(
        period=DateRange(start=date(2020, 1, 1), end=date(2020, 12, 31))
    )
    matching_contract.id = contract_repository.create(matching_contract)
    invalid_year = domainfactory.contract_year(matching_contract)
    invalid_year.year = 2025  # Outside contract period
    matching_position = domainfactory.contract_position(invalid_year)

    matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[matching_position],
    )
    matching_invoice.id = invoice_service.save(matching_invoice)

    valid_contract = domainfactory.contract(
        period=DateRange(start=date(2024, 1, 1), end=date(2024, 12, 31))
    )
    contract_repository.create(valid_contract)
    valid_position = domainfactory.contract_position(domainfactory.contract_year(valid_contract))

    non_matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[valid_position],
    )
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.HasErrorsCriterion())

    expected = list_item_from_invoice(matching_invoice, creditor.name)
    # has_invalid_contract_years is frozen on InvoiceListItem, so we construct a new one

    expected = replace(expected, has_invalid_contract_years=True)

    assert actual == [expected]


@pytest.mark.django_db
def test__searching_by_foreign_currency__finds_invoices_with_foreign_currency_no_conversion() -> (
    None
):
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    home_currency = Currency.EUR
    foreign_currency = Currency.USD

    matching_position = domainfactory.free_position(currency=foreign_currency)
    matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[matching_position],
    )
    matching_invoice.id = invoice_service.save(matching_invoice)

    non_matching_position = domainfactory.free_position(currency=home_currency)
    non_matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[non_matching_position],
    )
    non_matching_invoice.id = invoice_service.save(non_matching_invoice)

    actual = iq.search_to_list_items(iq.MissingCurrencyConversionCriterion(home_currency))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
def test__searching_by_missing_currency_conversion__excludes_invoices_without_positions() -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    home_currency = Currency.EUR
    foreign_currency = Currency.USD

    matching_position = domainfactory.free_position(currency=foreign_currency)
    matching_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[matching_position],
    )
    matching_invoice.id = invoice_service.save(matching_invoice)

    invoice_without_positions = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice_without_positions.id = invoice_service.save(invoice_without_positions)

    actual = iq.search_to_list_items(iq.MissingCurrencyConversionCriterion(home_currency))

    assert actual == [list_item_from_invoice(matching_invoice, creditor.name)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_list_view__searching_by_payment_status_via_http_request__finds_matching_invoices(
    client: Client,
) -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    unpaid_invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    unpaid_invoice.reset_payment()
    unpaid_invoice.id = invoice_service.save(unpaid_invoice)

    paid_invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    paid_invoice.pay()
    paid_invoice.id = invoice_service.save(paid_invoice)

    response = client.get("/invoices/list/", {"payment_status": "unpaid"})

    assert response.status_code == 200
    invoice_list = response.context["entities"]

    invoice_ids = [item.id for item in invoice_list]
    assert unpaid_invoice.id in invoice_ids
    assert paid_invoice.id not in invoice_ids


@pytest.mark.django_db
@pytest.mark.parametrize(
    "search_term",
    ["", "   ", "\t"],
)
def test__generic_search__empty_or_whitespace__returns_all_invoices(search_term: str) -> None:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    invoice1 = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice1.id = invoice_service.save(invoice1)
    invoice2 = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice2.id = invoice_service.save(invoice2)

    actual = iq.search_to_list_items(iq.GenericSearchCriterion(search_term))

    assert len(actual) == 2


@pytest.mark.django_db
def test__generic_search__multi_word_across_creditor_and_request_id__matches_independently_per_field() -> (
    None
):
    match = invoice_matching_request_id(creditor_name="ACS Publishing")
    request_id = match.query_str

    actual = iq.search_to_list_items(iq.GenericSearchCriterion(f"acs {request_id}"))

    assert len(actual) == 1
    assert actual[0].creditor_name == "ACS Publishing"


@pytest.mark.django_db
def test__generic_search__multi_word_across_different_fields__matches_independently_per_field() -> (
    None
):
    creditor = modelfactory.creditor(name="ACS Publishing")
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.id = invoice_service.save(invoice)

    actual = iq.search_to_list_items(iq.GenericSearchCriterion(f"acs {invoice.number}"))

    assert len(actual) == 1
    assert actual[0].creditor_name == "ACS Publishing"


@pytest.mark.django_db
def test__generic_search__multi_word_creditor__each_word_matches_independently() -> None:
    creditor = modelfactory.creditor(name="Alpha Beta Gamma")
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=())
    invoice.id = invoice_service.save(invoice)

    actual = iq.search_to_list_items(iq.GenericSearchCriterion("Alpha Gamma"))

    assert len(actual) == 1
    assert actual[0].creditor_name == "Alpha Beta Gamma"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__search_publications__multi_word_search__each_word_matches_independently(
    client: Client,
) -> None:
    modelfactory.fundingrequest("Nature Communications")

    response = client.post(
        reverse("invoices:pub_search"),
        {"q": "Nat Comm"},
    )

    assert response.status_code == 200
    assert "Nature Communications" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingsource_list_view__multi_word_search__each_word_matches_independently(
    client: Client,
) -> None:

    modelfactory.budget(name="Alpha Beta Gamma")

    response = client.get(reverse("invoices:fundingsource_list"), {"query": "Alpha Gamma"})

    assert response.status_code == 200
    assert "Alpha Beta Gamma" in response.content.decode()

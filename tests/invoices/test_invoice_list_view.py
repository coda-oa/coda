from datetime import date
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import parse_html
from django.urls import reverse

from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, Invoice, PaymentStatus
from tests import domainfactory, modelfactory
from tests.filterdom import (
    chip_texts,
    clear_all_text,
    is_checked,
    rendered_field_names,
    selected_option_values,
    swap_targets,
)


def goto_list_page(
    client: Client,
    query: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:list"), data=query))


def get_list_region(
    client: Client,
    query: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:list_region"), data=query))


def create_invoice(
    number: str,
    *,
    invoice_date: date | None = None,
    status: str | None = None,
) -> Invoice:
    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number=number,
        date=invoice_date or date(2024, 6, 1),
        creditor=CreditorId(creditor.pk),
        positions=(),
        status=PaymentStatus(status) if status else PaymentStatus.Unpaid,
    )
    invoice.id = invoice_service.save(invoice)
    return invoice


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__returns_list_and_sidebar_not_toolbar(client: Client) -> None:
    create_invoice("REGION-42")

    html = get_list_region(client).content.decode()

    assert "REGION-42" in html
    names = rendered_field_names(parse_html(html))
    assert "payment_status" in names
    assert names.isdisjoint({"search_term", "sort_by"})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_list_region__rerenders_the_sidebar_from_the_url(client: Client) -> None:
    html = get_list_region(client, {"payment_status": "unpaid"}).content.decode()

    dom = parse_html(html)
    assert "filter-sidebar-form" in swap_targets(dom)
    assert selected_option_values(dom, "payment_status") == ["unpaid"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__is_zero_without_filters(client: Client) -> None:
    assert goto_list_page(client).context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__counts_each_active_param(client: Client) -> None:
    budget = modelfactory.budget()
    contract = modelfactory.contract()

    response = goto_list_page(
        client,
        {
            "payment_status": "unpaid",
            "funding_source": str(budget.pk),
            "contract_name": str(contract.pk),
            "contract_year": "2024",
            "date_start": "2024-01-01",
            "date_end": "2024-12-31",
            "has_external_id": "true",
            "has_foreign_currency": "true",
            "has_errors": "true",
        },
    )

    assert response.context["filter_count"] == 9


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__excludes_search_and_sort(client: Client) -> None:
    response = goto_list_page(client, {"search_term": "x", "sort_by": "alphabetical"})

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clear_all__shown_with_active_filters(client: Client) -> None:
    html = get_list_region(client, {"payment_status": "unpaid"}).content.decode()

    assert clear_all_text(html) == "Clear all"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clear_all__hidden_without_filters(client: Client) -> None:
    assert clear_all_text(get_list_region(client).content.decode()) is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_payment_status(client: Client) -> None:
    response = goto_list_page(client, {"payment_status": "paid"})

    assert selected_option_values(parse_html(response.content.decode()), "payment_status") == [
        "paid",
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_switch_checked(client: Client) -> None:
    response = goto_list_page(client, {"has_errors": "true"})

    assert is_checked(parse_html(response.content.decode()), "has_errors")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__active_filter_chips__one_per_active_param_with_remove_urls(client: Client) -> None:
    response = goto_list_page(client, {"payment_status": "unpaid", "contract_year": "2024"})

    chips = response.context["active_filters"]
    assert {chip.text for chip in chips} == {"unpaid", "Year 2024"}

    unpaid = next(chip for chip in chips if chip.text == "unpaid")
    assert unpaid.source_id == "payment_status"
    assert unpaid.kind == "neutral"
    assert "contract_year=2024" in unpaid.remove_url
    assert "payment_status" not in unpaid.remove_url
    assert unpaid.remove_fragment_url.startswith(reverse("invoices:list_region"))

    assert chip_texts(parse_html(response.content.decode())) == ["unpaid", "Year 2024"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__active_filter_chips__contract_shows_contract_name(client: Client) -> None:
    contract = modelfactory.contract()

    response = goto_list_page(client, {"contract_name": str(contract.pk)})

    chips = response.context["active_filters"]
    assert [(chip.text, chip.source_id) for chip in chips] == [(contract.name, "contract_name")]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__date_range__narrows_invoice_list(client: Client) -> None:
    create_invoice("IN-RANGE", invoice_date=date(2024, 6, 1))
    create_invoice("OUT-RANGE", invoice_date=date(2025, 6, 1))

    html = get_list_region(
        client, {"date_start": "2024-01-01", "date_end": "2024-12-31"}
    ).content.decode()

    assert "IN-RANGE" in html
    assert "OUT-RANGE" not in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funding_source__narrows_to_invoices_with_matching_position(client: Client) -> None:
    creditor_id = CreditorId(modelfactory.creditor().pk)
    matching_budget = funding_source_repository.create(domainfactory.budget())
    other_budget = funding_source_repository.create(domainfactory.budget())

    matching_position = domainfactory.free_position()
    matching_position.assign_funding(
        Budget(matching_budget, "matching"), matching_position.cost.amount
    )
    matching = Invoice.new(
        number="FUNDED-MATCH",
        date=date(2024, 6, 1),
        creditor=creditor_id,
        positions=[matching_position],
    )
    matching.id = invoice_service.save(matching)

    other_position = domainfactory.free_position()
    other_position.assign_funding(Budget(other_budget, "other"), other_position.cost.amount)
    other = Invoice.new(
        number="FUNDED-OTHER",
        date=date(2024, 6, 1),
        creditor=creditor_id,
        positions=[other_position],
    )
    other.id = invoice_service.save(other)

    html = get_list_region(client, {"funding_source": str(matching_budget)}).content.decode()

    assert "FUNDED-MATCH" in html
    assert "FUNDED-OTHER" not in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sort_by_alphabetical__orders_entities(client: Client) -> None:
    create_invoice("Z-001", invoice_date=date(2024, 6, 1))
    create_invoice("A-001", invoice_date=date(2024, 1, 1))

    alphabetical = goto_list_page(client, {"sort_by": "alphabetical"})
    assert [item.number for item in alphabetical.context["entities"]] == ["A-001", "Z-001"]

    default = goto_list_page(client)
    assert [item.number for item in default.context["entities"]] == ["Z-001", "A-001"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__empty_state__shown_when_no_match(client: Client) -> None:
    html = get_list_region(
        client, {"search_term": "definitely-no-such-invoice-xyz"}
    ).content.decode()

    assert "No invoices match the selected filters." in html
    assert "Clear all filters" in html

import re
from datetime import date

import pytest
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import CreditorId, Invoice, PaymentStatus
from tests import modelfactory
from tests.page_objects import filter_ui_expectations, filter_ui_selectors
from tests.page_objects.invoice_list_page import InvoiceListPage


def create_invoice(
    number: str,
    *,
    status: PaymentStatus = PaymentStatus.Unpaid,
    invoice_date: date = date(2024, 6, 1),
) -> None:
    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number=number,
        date=invoice_date,
        creditor=CreditorId(creditor.pk),
        positions=(),
        status=status,
    )
    invoice.id = invoice_service.save(invoice)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__invoice_live_search__typing_narrows_region_in_place(
    coda_page: Page, live_server: LiveServer
) -> None:
    create_invoice("LIVE-MATCH-001")
    create_invoice("LIVE-OTHER-001")

    list_page = InvoiceListPage(coda_page, live_server.url)
    list_page.navigate()

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "LIVE-MATCH-001"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "LIVE-OTHER-001"
    )

    list_page.type_search("LIVE-MATCH")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "LIVE-OTHER-001"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "LIVE-MATCH-001"
    )
    filter_ui_expectations.expect_url_query(coda_page, "search_term=LIVE-MATCH")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__search_clear_icon__resets_filter_in_place(
    coda_page: Page, live_server: LiveServer
) -> None:
    create_invoice("CLEAR-MATCH-001")
    create_invoice("CLEAR-OTHER-001")

    list_page = InvoiceListPage(coda_page, live_server.url)
    list_page.navigate()

    list_page.type_search("CLEAR-MATCH")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CLEAR-OTHER-001"
    )

    list_page.clear_search()

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CLEAR-OTHER-001"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CLEAR-MATCH-001"
    )
    filter_ui_expectations.expect_no_url_query(coda_page, "search_term=CLEAR-MATCH")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__sort_change__reorders_list_in_place(coda_page: Page, live_server: LiveServer) -> None:
    create_invoice("ZZ-001", invoice_date=date(2024, 6, 1))
    create_invoice("AA-001", invoice_date=date(2024, 1, 1))

    list_page = InvoiceListPage(coda_page, live_server.url)
    list_page.navigate()

    filter_ui_expectations.expect_text_before(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "ZZ-001", "AA-001"
    )

    list_page.sort_by("alphabetical")
    filter_ui_expectations.expect_text_before(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "AA-001", "ZZ-001"
    )
    filter_ui_expectations.expect_url_query(coda_page, "sort_by=alphabetical")

    list_page.sort_by("date_desc")

    filter_ui_expectations.expect_text_before(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "ZZ-001", "AA-001"
    )
    filter_ui_expectations.expect_url_query(coda_page, "sort_by=date_desc")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__invoice_active_filter_chips__summary_shows_and_removes_in_place(
    coda_page: Page, live_server: LiveServer
) -> None:
    create_invoice("CHIP-UNPAID", status=PaymentStatus.Unpaid)
    create_invoice("CHIP-PAID", status=PaymentStatus.Paid)

    list_page = InvoiceListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.filter_by_payment_status("unpaid")

    filter_ui_expectations.expect_active_filter(coda_page, "unpaid")
    filter_ui_expectations.expect_filter_count(coda_page, 1)
    filter_ui_expectations.expect_clear_all(coda_page)
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CHIP-UNPAID"
    )
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CHIP-PAID"
    )

    list_page.remove_active_filter("unpaid")

    filter_ui_expectations.expect_active_filter_count(coda_page, 0)
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CHIP-PAID"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.INVOICE_LIST), "CHIP-UNPAID"
    )
    filter_ui_expectations.expect_no_url_query(coda_page, "payment_status=unpaid")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__chip_removal__resets_sidebar_controls(coda_page: Page, live_server: LiveServer) -> None:
    contract = modelfactory.contract()

    list_page = InvoiceListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.filter_by_payment_status("paid")
    list_page.set_contract_year("2024")
    list_page.set_date_start("2024-01-01")
    list_page.show_only_errors()
    list_page.choose_contract(contract.name)

    for name in ("paid", "Year 2024", "From 2024-01-01", "With errors", contract.name):
        filter_ui_expectations.expect_active_filter(coda_page, name)
    for name in ("paid", "Year 2024", "From 2024-01-01", "With errors", contract.name):
        list_page.remove_active_filter(name)

    filter_ui_expectations.expect_control_value(coda_page, filter_ui_selectors.PAYMENT_STATUS, "")
    filter_ui_expectations.expect_control_value(coda_page, filter_ui_selectors.CONTRACT_YEAR, "")
    filter_ui_expectations.expect_control_value(coda_page, filter_ui_selectors.DATE_START, "")
    filter_ui_expectations.expect_unchecked_control(coda_page, filter_ui_selectors.HAS_ERRORS)
    filter_ui_expectations.expect_control_value(coda_page, filter_ui_selectors.CONTRACT_NAME, "")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__toolbar_filter_count__tracks_mobile_filter_and_chip_removal(
    coda_page: Page, live_server: LiveServer
) -> None:
    list_page = InvoiceListPage(coda_page, live_server.url)
    list_page.navigate()
    coda_page.set_viewport_size({"width": 900, "height": 900})
    coda_page.locator(filter_ui_selectors.FILTER_DRAWER_TOGGLE).click()
    expect(coda_page.locator(filter_ui_selectors.FILTER_LAYOUT)).to_have_class(
        re.compile("filter-drawer-open")
    )

    list_page.filter_by_payment_status("unpaid")

    toolbar_count = coda_page.locator(filter_ui_selectors.TOOLBAR_FILTER_COUNT)
    expect(toolbar_count).to_be_visible()
    expect(toolbar_count).to_have_text("1")

    list_page.remove_active_filter("unpaid")

    expect(toolbar_count).to_have_count(1)
    expect(toolbar_count).to_be_hidden()

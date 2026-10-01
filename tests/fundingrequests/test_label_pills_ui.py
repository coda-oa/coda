import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from tests import modelfactory
from tests.page_objects import filter_ui_expectations, filter_ui_selectors
from tests.page_objects.fundingrequest_list_page import FundingRequestListPage


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__label_pill__click_updates_list_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    alpha = label_create("E2E Alpha", Color.from_rgb(255, 0, 0))
    matching = modelfactory.fundingrequest(title="E2E pill match")
    label_attach(matching, alpha)
    modelfactory.fundingrequest(title="E2E pill non-match")

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "E2E pill match"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "E2E pill non-match"
    )

    list_page.click_label_pill("E2E Alpha")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "E2E pill non-match"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "E2E pill match"
    )

    filter_ui_expectations.expect_clear_all(coda_page)
    filter_ui_expectations.expect_url_query(coda_page, "labels=")

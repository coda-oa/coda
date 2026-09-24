import re
from datetime import date

import pytest
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest
from tests import domainfactory, modelfactory
from tests.page_objects import filter_ui_expectations, filter_ui_selectors
from tests.page_objects.fundingrequest_list_page import FundingRequestListPage


def _create_article_and_monograph_titles() -> tuple[str, str]:
    article = modelfactory.fundingrequest(title="E2E filter article")
    monograph_request_id = repository.create(
        FundingRequest.new(
            domainfactory.monograph(publisher=PublisherId(modelfactory.publisher().pk)),
            domainfactory.payment(),
        )
    )
    monograph = FundingRequestModel.objects.get(pk=monograph_request_id)

    return article.publication.title, monograph.publication.title


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__filter_forms__values_are_sent_with_region_updates(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    article_title, monograph_title = _create_article_and_monograph_titles()
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), article_title
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), monograph_title
    )

    list_page.select_publication_type("article")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), monograph_title
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), article_title
    )
    filter_ui_expectations.expect_url_query(coda_page, "publication_type=article")

    list_page.type_search("zzz-no-such-title")
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "No funding requests match"
    )
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), article_title
    )


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__search_blur__avoids_duplicate_and_clears_search_once(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    article = modelfactory.fundingrequest(title="E2E search clear")
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    search_requests: list[str] = []
    coda_page.on(
        "request",
        lambda request: (
            search_requests.append(request.url)
            if "/fundingrequests/list/region/" in request.url
            else None
        ),
    )
    search = coda_page.locator(filter_ui_selectors.FILTER_SEARCH)
    with coda_page.expect_request(lambda request: "/fundingrequests/list/region/" in request.url):
        search.fill("no-matching-title")
    coda_page.wait_for_function(filter_ui_selectors.HTMX_IDLE_EXPRESSION)
    assert len(search_requests) == 1

    search.press("Tab")
    coda_page.wait_for_timeout(100)
    assert len(search_requests) == 1

    with coda_page.expect_request(lambda request: "/fundingrequests/list/region/" in request.url):
        search.evaluate(
            "element => {"
            " element.value = '';"
            " element.dispatchEvent(new Event('change', { bubbles: true }));"
            "}"
        )
    coda_page.wait_for_function(filter_ui_selectors.HTMX_IDLE_EXPRESSION)
    expect(coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST)).to_contain_text(
        article.publication.title
    )
    assert len(search_requests) == 2

    with coda_page.expect_request(lambda request: "/fundingrequests/list/region/" in request.url):
        search.fill("no-second-match")
    coda_page.wait_for_function(filter_ui_selectors.HTMX_IDLE_EXPRESSION)
    assert len(search_requests) == 3

    with coda_page.expect_request(lambda request: "/fundingrequests/list/region/" in request.url):
        search.evaluate(
            "element => {"
            " element.value = '';"
            " element.dispatchEvent(new Event('input', { bubbles: true }));"
            " element.dispatchEvent(new Event('change', { bubbles: true }));"
            "}"
        )
    coda_page.wait_for_function(filter_ui_selectors.HTMX_IDLE_EXPRESSION)
    expect(coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST)).to_contain_text(
        article.publication.title
    )
    assert len(search_requests) == 4


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__filter_forms__keep_label_filter_set_by_pills(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    label = label_create("E2E State", Color.from_rgb(0, 128, 0))
    labeled = modelfactory.fundingrequest(title="E2E state labeled")
    label_attach(labeled, label)
    unlabeled = modelfactory.fundingrequest(title="E2E state unlabeled")
    labeled_title = labeled.publication.title
    unlabeled_title = unlabeled.publication.title

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), labeled_title
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), unlabeled_title
    )

    list_page.click_label_pill("E2E State")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), unlabeled_title
    )

    list_page.select_publication_type("article")
    filter_ui_expectations.expect_url_query(coda_page, "publication_type=article")

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), labeled_title
    )
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), unlabeled_title
    )
    filter_ui_expectations.expect_url_query(coda_page, f"labels={label.pk}")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__active_filter_chips__summary_shows_and_removes_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    alpha = label_create("Alpha chip", Color.from_rgb(255, 0, 0))
    beta = label_create("Beta chip", Color.from_rgb(0, 0, 255))
    label_attach(modelfactory.fundingrequest(title="Alpha chip paper"), alpha)
    label_attach(modelfactory.fundingrequest(title="Beta chip paper"), beta)

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.click_label_pill("Alpha chip")
    list_page.click_label_pill("Beta chip")

    filter_ui_expectations.expect_active_filter(coda_page, "Alpha chip")
    filter_ui_expectations.expect_active_filter(coda_page, "Beta chip")
    filter_ui_expectations.expect_filter_count(coda_page, 2)
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Alpha chip paper"
    )

    list_page.remove_active_filter("Alpha chip")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Alpha chip paper"
    )

    filter_ui_expectations.expect_active_filter_count(coda_page, 1)
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Beta chip paper"
    )
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Alpha chip paper"
    )
    filter_ui_expectations.expect_url_query(coda_page, f"labels={beta.pk}")
    filter_ui_expectations.expect_no_url_query(coda_page, f"labels={alpha.pk}")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__chip_removal__resets_sidebar_controls(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    contract = modelfactory.contract()

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.filter_by_processing_status("approved")
    list_page.filter_by_payment_status("paid")
    list_page.select_publication_type("article")
    list_page.choose_contract(contract.name)
    list_page.show_only_invalid_contract_years()

    chip_names = ("approved", "Paid", "Article", contract.name, "Invalid years only")
    for name in chip_names:
        filter_ui_expectations.expect_active_filter(coda_page, name)
    for name in chip_names:
        list_page.remove_active_filter(name)

    filter_ui_expectations.expect_no_selected_options(
        coda_page, filter_ui_selectors.PROCESSING_STATUS
    )
    filter_ui_expectations.expect_no_selected_options(
        coda_page, filter_ui_selectors.ID_PAYMENT_STATUS
    )
    filter_ui_expectations.expect_checked_control(
        coda_page, filter_ui_selectors.PUBLICATION_TYPE_ALL
    )
    filter_ui_expectations.expect_unchecked_control(
        coda_page, filter_ui_selectors.PUBLICATION_TYPE_ARTICLE
    )
    filter_ui_expectations.expect_control_value(coda_page, filter_ui_selectors.CONTRACT_NAME, "")
    filter_ui_expectations.expect_unchecked_control(
        coda_page, filter_ui_selectors.INVALID_CONTRACT_YEARS
    )


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__contract_select__enter_updates_filter_chip_and_count(
    coda_page: Page, live_server: LiveServer
) -> None:
    contract = modelfactory.contract()
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    search_box = coda_page.locator(filter_ui_selectors.CONTRACT_NAME).locator(
        filter_ui_selectors.SEARCH_SELECT_BOX
    )
    search_box.click()
    search_box.press_sequentially(contract.name)
    search_box.press("Enter")

    filter_ui_expectations.expect_url_query(coda_page, f"contract_name={contract.pk}")
    filter_ui_expectations.expect_active_filter(coda_page, contract.name)
    filter_ui_expectations.expect_active_filter_count(coda_page, 1)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__sort_change__reorders_list_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    alpha = modelfactory.fundingrequest(title="AA-alpha request")
    zulu = modelfactory.fundingrequest(title="ZZ-zulu request")
    FundingRequestModel.objects.filter(pk=alpha.pk).update(request_date=date(2024, 1, 1))
    FundingRequestModel.objects.filter(pk=zulu.pk).update(request_date=date(2024, 6, 1))

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    filter_ui_expectations.expect_text_before(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST),
        "ZZ-zulu request",
        "AA-alpha request",
    )

    list_page.sort_by("alphabetical")

    filter_ui_expectations.expect_text_before(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST),
        "AA-alpha request",
        "ZZ-zulu request",
    )
    filter_ui_expectations.expect_url_query(coda_page, "sort_by=alphabetical")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__search_clear_icon__resets_filter_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    modelfactory.fundingrequest(title="Clear hit request")
    modelfactory.fundingrequest(title="Clear other request")

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    list_page.type_search("Clear hit")
    filter_ui_expectations.expect_no_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Clear other request"
    )

    list_page.clear_search()

    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Clear other request"
    )
    filter_ui_expectations.expect_text(
        coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST), "Clear hit request"
    )
    filter_ui_expectations.expect_no_url_query(coda_page, "search_term=Clear+hit")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__chip_removal__keeps_other_values_of_a_multi_value_filter(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.filter_by_processing_status("approved")
    list_page.filter_by_processing_status("rejected")
    filter_ui_expectations.expect_active_filter(coda_page, "approved")
    filter_ui_expectations.expect_active_filter(coda_page, "rejected")

    list_page.remove_active_filter("approved")

    filter_ui_expectations.expect_selected_options(
        coda_page, filter_ui_selectors.PROCESSING_STATUS, ["rejected"]
    )
    filter_ui_expectations.expect_active_filter_count(coda_page, 1)
    filter_ui_expectations.expect_url_query(coda_page, "processing_status=rejected")
    filter_ui_expectations.expect_no_url_query(coda_page, "processing_status=approved")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__deep_linked_selection__survives_the_next_filter_change(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate("processing_status=approved")
    filter_ui_expectations.expect_selected_options(
        coda_page, filter_ui_selectors.PROCESSING_STATUS, ["approved"]
    )

    list_page.select_publication_type("article")

    filter_ui_expectations.expect_url_query(coda_page, "processing_status=approved")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__mobile_drawer__focuses_drawer_and_tabs_to_close_button(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    coda_page.set_viewport_size({"width": 900, "height": 900})
    # Avoid scroll-container focusability masking the drawer's explicit focus target.
    coda_page.locator(filter_ui_selectors.FILTER_SIDEBAR_CLASS).evaluate(
        "sidebar => { sidebar.style.overflow = 'visible'; }"
    )
    coda_page.locator(filter_ui_selectors.FILTER_DRAWER_TOGGLE).click()

    expect(coda_page.locator(filter_ui_selectors.FILTER_SIDEBAR)).to_be_focused()
    coda_page.keyboard.press("Tab")
    expect(coda_page.locator(filter_ui_selectors.FILTER_DRAWER_CLOSE)).to_be_focused()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__sidebar_rerender__keeps_mobile_drawer_open(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    coda_page.set_viewport_size({"width": 900, "height": 900})
    coda_page.locator(filter_ui_selectors.FILTER_DRAWER_TOGGLE).click()
    expect(coda_page.locator(filter_ui_selectors.FILTER_LAYOUT)).to_have_class(
        re.compile("filter-drawer-open")
    )

    list_page.select_publication_type("article")

    expect(coda_page.locator(filter_ui_selectors.FILTER_LAYOUT)).to_have_class(
        re.compile("filter-drawer-open")
    )


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__sidebar_rerender__keeps_hydrated_selection_in_the_next_request(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """A re-rendered widget must still contribute its server-rendered value."""
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate("processing_status=approved")

    list_page.select_publication_type("article")

    filter_ui_expectations.expect_selected_options(
        coda_page, filter_ui_selectors.PROCESSING_STATUS, ["approved"]
    )
    list_page.show_only_invalid_contract_years()
    filter_ui_expectations.expect_url_query(coda_page, "processing_status=approved")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__toolbar_filter_count__tracks_mobile_filter_and_chip_removal(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    coda_page.set_viewport_size({"width": 900, "height": 900})
    coda_page.locator(filter_ui_selectors.FILTER_DRAWER_TOGGLE).click()
    expect(coda_page.locator(filter_ui_selectors.FILTER_LAYOUT)).to_have_class(
        re.compile("filter-drawer-open")
    )

    list_page.filter_by_processing_status("approved")

    toolbar_count = coda_page.locator(filter_ui_selectors.TOOLBAR_FILTER_COUNT)
    expect(toolbar_count).to_be_visible()
    expect(toolbar_count).to_have_text("1")

    list_page.remove_active_filter("approved")

    expect(toolbar_count).to_have_count(1)
    expect(toolbar_count).to_be_hidden()

import re

from django.urls import reverse
from playwright.sync_api import Page

from tests.page_objects import filter_ui_selectors


class FundingRequestListPage:
    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url
        self._list_region = page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST)
        self._active_filters = page.locator(filter_ui_selectors.ACTIVE_FILTERS)
        self._search_input = page.locator(filter_ui_selectors.FILTER_SEARCH)

    # Navigation

    def navigate(self, query: str = "") -> None:
        # Sidebar filter UI is only rendered at desktop width.
        self._page.set_viewport_size({"width": 1440, "height": 900})
        url = self._base_url + reverse("fundingrequests:list")
        self._page.goto(f"{url}?{query}" if query else url)
        self._page.wait_for_function("() => typeof htmx !== 'undefined'")
        # Readiness guard: fail fast here (sync, not a business assertion) if the page
        # chrome never renders, instead of inside the first test assertion.
        self._list_region.wait_for()

    # Actions

    def select_publication_type(self, value: str) -> None:
        self._page.locator(f'label[for="publication_type_{value}"]').click()
        self._wait_for_settled()

    def filter_by_processing_status(self, value: str) -> None:
        self._pick_option(filter_ui_selectors.PROCESSING_STATUS, value)

    def sort_by(self, value: str) -> None:
        self._page.select_option(filter_ui_selectors.FILTER_SORT, value)
        self._wait_for_settled()

    def filter_by_payment_status(self, value: str) -> None:
        self._pick_option(filter_ui_selectors.ID_PAYMENT_STATUS, value)

    def choose_contract(self, name: str) -> None:
        host = self._page.locator(filter_ui_selectors.CONTRACT_NAME)
        host.locator(filter_ui_selectors.SEARCH_SELECT_BOX).click()
        host.locator(filter_ui_selectors.SEARCH_SELECT_OPTION_ITEM).filter(
            has_text=name
        ).first.click()
        self._wait_for_settled()

    def show_only_invalid_contract_years(self) -> None:
        self._page.check(filter_ui_selectors.INVALID_CONTRACT_YEARS)
        self._wait_for_settled()

    def type_search(self, term: str) -> None:
        self._search_input.press_sequentially(term, delay=50)

    def clear_search(self) -> None:
        # Emulates the browser's <input type=search> clear icon: it sets the
        # value to empty and fires `input` — not keyup, and not change either.
        self._page.eval_on_selector(
            filter_ui_selectors.FILTER_SEARCH,
            "el => { el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true })); }",
        )
        self._wait_for_settled()

    def click_label_pill(self, name: str) -> None:
        self._page.locator(f'{filter_ui_selectors.LABEL_FILTER_PILL}:text-is("{name}")').click()
        self._wait_for_settled()

    def remove_active_filter(self, name: str) -> None:
        chip = self._active_filters.locator(filter_ui_selectors.ACTIVE_FILTER).filter(has_text=name)
        chip.locator(filter_ui_selectors.ACTIVE_FILTER_REMOVE).click()
        chip.wait_for(state="detached")
        self._wait_for_settled()

    # Internals

    def _pick_option(self, host_selector: str, option_text: str) -> None:
        # Opens the search-select-multi dropdown and clicks the matching option.
        host = self._page.locator(host_selector)
        host.locator(filter_ui_selectors.SEARCH_SELECT_MULTI_INPUT).click()
        host.locator(filter_ui_selectors.SEARCH_SELECT_OPTION).filter(
            has_text=re.compile(rf"^{option_text}$", re.IGNORECASE)
        ).first.click()
        self._wait_for_settled()

    def _wait_for_settled(self) -> None:
        # htmx marks in-flight elements with `.htmx-request`; no in-flight
        # element means the last filter update finished swapping.
        self._page.wait_for_function(filter_ui_selectors.HTMX_IDLE_EXPRESSION)

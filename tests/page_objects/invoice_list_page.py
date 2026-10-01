from django.urls import reverse
from playwright.sync_api import Page

from tests.page_objects import filter_ui_selectors


class InvoiceListPage:
    """Drives the invoice list the way a user does: through the filter controls."""

    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url
        self._list_region = page.locator(filter_ui_selectors.INVOICE_LIST)
        self._active_filters = page.locator(filter_ui_selectors.ACTIVE_FILTERS)
        self._search_input = page.locator(filter_ui_selectors.FILTER_SEARCH)

    # Navigation

    def navigate(self) -> None:
        # Sidebar filter UI is only rendered at desktop width.
        self._page.set_viewport_size({"width": 1440, "height": 900})
        self._page.goto(self._base_url + reverse("invoices:list"))
        self._page.wait_for_function("() => typeof htmx !== 'undefined'")
        # Readiness guard: fail fast here (sync, not a business assertion) if the page
        # chrome never renders, instead of inside the first test assertion.
        self._list_region.wait_for()

    # Filter actions (each triggers the live list update)
    def sort_by(self, value: str) -> None:
        self._page.select_option(filter_ui_selectors.FILTER_SORT, value)
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

    def filter_by_payment_status(self, status: str) -> None:
        self._page.select_option(filter_ui_selectors.PAYMENT_STATUS, status)
        self._wait_for_settled()

    def set_contract_year(self, year: str) -> None:
        self._commit_value(filter_ui_selectors.CONTRACT_YEAR, year)

    def set_date_start(self, value: str) -> None:
        self._commit_value(filter_ui_selectors.DATE_START, value)

    def show_only_errors(self) -> None:
        self._page.check(filter_ui_selectors.HAS_ERRORS)
        self._wait_for_settled()

    def choose_contract(self, name: str) -> None:
        host = self._page.locator(filter_ui_selectors.CONTRACT_NAME)
        host.locator(filter_ui_selectors.SEARCH_SELECT_BOX).click()
        host.locator(filter_ui_selectors.SEARCH_SELECT_OPTION_ITEM).filter(
            has_text=name
        ).first.click()
        self._wait_for_settled()

    def remove_active_filter(self, name: str) -> None:
        chip = self._active_filters.locator(filter_ui_selectors.ACTIVE_FILTER).filter(has_text=name)
        chip.locator(filter_ui_selectors.ACTIVE_FILTER_REMOVE).click()
        chip.wait_for(state="detached")

    # Internals

    def _commit_value(self, selector: str, value: str) -> None:
        # The sidebar reacts to `change`, which fires when the field is left.
        field = self._page.locator(selector)
        field.fill(value)
        field.blur()
        self._wait_for_settled()

    def _wait_for_settled(self) -> None:
        # htmx marks in-flight elements with `.htmx-request`; no in-flight
        # element means the last filter update finished swapping.
        self._page.wait_for_function(filter_ui_selectors.HTMX_IDLE_EXPRESSION)

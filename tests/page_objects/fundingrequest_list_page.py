import re

from django.urls import reverse
from playwright.sync_api import Page, expect


class FundingRequestListPage:
    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url
        self._list_region = page.locator("#fundingrequest-list")
        self._active_filters = page.locator("#active-filters")
        self._search_input = page.locator(".filter-search")
        self._filter_count_badge = page.locator("#filter-sidebar-header .filter-count")
        self._clear_all_button = page.locator("#filter-sidebar-header .filter-clear")

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
        self._pick_option("#processing_status", value)

    def sort_by(self, value: str) -> None:
        self._page.select_option("#sort_by", value)
        self._wait_for_settled()

    def filter_by_payment_status(self, value: str) -> None:
        self._pick_option("#id_payment_status", value)

    def choose_contract(self, name: str) -> None:
        host = self._page.locator("#contract_name")
        host.locator("#search-box").click()
        host.locator("li").filter(has_text=name).first.click()
        self._wait_for_settled()

    def show_only_invalid_contract_years(self) -> None:
        self._page.check("#invalid_contract_years")
        self._wait_for_settled()

    def type_search(self, term: str) -> None:
        self._search_input.press_sequentially(term, delay=50)

    def clear_search(self) -> None:
        # Emulates the browser's <input type=search> clear icon: it sets the
        # value to empty and fires `input` — not keyup, and not change either.
        self._page.eval_on_selector(
            ".filter-search",
            "el => { el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true })); }",
        )
        self._wait_for_settled()

    def click_label_pill(self, name: str) -> None:
        self._page.locator(f'.label-filter-pill:text-is("{name}")').click()
        self._wait_for_settled()

    def remove_active_filter(self, name: str) -> None:
        chip = self._active_filters.locator(f'.active-filter:has-text("{name}")')
        chip.locator(".active-filter-remove").click()
        chip.wait_for(state="detached")
        self._wait_for_settled()

    # Results region

    def should_show_request(self, title: str) -> None:
        expect(self._list_region).to_contain_text(title)

    def should_show_request_before(self, first: str, second: str) -> None:
        expect(self._list_region).to_have_text(re.compile(rf".*{first}.*{second}.*", re.DOTALL))

    def should_not_show_request(self, title: str) -> None:
        expect(self._list_region).not_to_contain_text(title)

    def should_show_empty_state(self) -> None:
        expect(self._list_region).to_contain_text("No funding requests match")

    # Filter state surfaced back to the user

    def should_show_active_filter(self, name: str) -> None:
        expect(self._active_filters.locator(f'.active-filter:has-text("{name}")')).to_be_visible()

    def should_have_active_filter_count(self, count: int) -> None:
        expect(self._active_filters.locator(".active-filter")).to_have_count(count)

    def should_have_filter_count(self, count: int) -> None:
        expect(self._filter_count_badge).to_have_text(str(count))

    def should_show_clear_all(self) -> None:
        expect(self._clear_all_button).to_have_text("Clear all")

    def should_have_url_query(self, fragment: str) -> None:
        expect(self._page).to_have_url(re.compile(re.escape(fragment)))

    def should_not_have_url_query(self, fragment: str) -> None:
        expect(self._page).not_to_have_url(re.compile(re.escape(fragment)))

    def should_have_form_value(self, selector: str, value: str) -> None:
        # Form-associated custom elements are not input elements, so poll the
        # `value` property directly instead of using to_have_value.
        self._page.wait_for_function(
            """([sel, expected]) => {
                const el = document.querySelector(sel);
                return el !== null && el.value === expected;
            }""",
            arg=[selector, value],
        )

    def should_be_checked(self, selector: str) -> None:
        expect(self._page.locator(selector)).to_be_checked()

    def should_have_unchecked_control(self, selector: str) -> None:
        expect(self._page.locator(selector)).not_to_be_checked()

    def should_have_no_selected_options(self, selector: str) -> None:
        expect(self._page.locator(selector).locator(".selected-tag")).to_have_count(0)

    def should_have_selected_options(self, selector: str, texts: list[str]) -> None:
        tags = self._page.locator(selector).locator(".selected-tag")
        expect(tags).to_have_count(len(texts))
        for text in texts:
            expect(tags.filter(has_text=text).first).to_be_visible()

    # Internals

    def _pick_option(self, host_selector: str, option_text: str) -> None:
        # Opens the search-select-multi dropdown and clicks the matching option.
        host = self._page.locator(host_selector)
        host.locator(".search-input").click()
        host.locator(".option").filter(
            has_text=re.compile(rf"^{option_text}$", re.IGNORECASE)
        ).first.click()
        self._wait_for_settled()

    def _wait_for_settled(self) -> None:
        # htmx marks in-flight elements with `.htmx-request`; no in-flight
        # element means the last filter update finished swapping.
        self._page.wait_for_function("() => !document.querySelector('.htmx-request')")

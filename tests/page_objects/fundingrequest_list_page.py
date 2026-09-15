import re
from urllib.parse import urlencode

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

    def navigate(self, *, label_ids: list[int] | None = None) -> None:
        query = urlencode([("labels", str(pk)) for pk in label_ids or []])
        url = self._base_url + reverse("fundingrequests:list")
        if query:
            url = f"{url}?{query}"
        # Sidebar filter UI is only rendered at desktop width.
        self._page.set_viewport_size({"width": 1440, "height": 900})
        self._page.goto(url)
        self._page.wait_for_function("() => typeof htmx !== 'undefined'")
        # Readiness guard: fail fast here (sync, not a business assertion) if the page
        # chrome never renders, instead of inside the first test assertion.
        self._list_region.wait_for()

    # Actions

    def select_publication_type(self, value: str) -> None:
        self._page.locator(f'label[for="publication_type_{value}"]').click()

    def type_search(self, term: str) -> None:
        self._search_input.press_sequentially(term, delay=50)

    def click_label_pill(self, name: str) -> None:
        self._page.locator(f'.label-filter-pill:text-is("{name}")').click()

    def remove_active_filter(self, name: str) -> None:
        self._active_filters.locator(
            f'.active-filter:has-text("{name}") .active-filter-remove'
        ).click()

    # Results region

    def should_show_request(self, title: str) -> None:
        expect(self._list_region).to_contain_text(title)

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

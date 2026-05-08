from django.urls import reverse
from playwright.sync_api import Page, expect


class FundingRequestArticleMetaPage:
    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url

    def navigate(self, funding_request_id: int) -> None:
        url = f"{self._base_url}{reverse('fundingrequests:update_publication', args=[funding_request_id])}"
        self._page.goto(url)

    def click_next_to_journal_step(self) -> None:
        self._page.get_by_role("button", name="Next").click()
        self._page.locator("#journal-search-results").wait_for()

    def search_for_journal(self, search_term: str = "") -> None:
        self._page.locator("#journal_title").fill(search_term)
        self._page.get_by_role("button", name="Search").click()
        # Wait for search results to load
        self._page.locator("#journal-search-results").wait_for()

    def click_create_new_journal_button(self) -> None:
        self._page.get_by_role("button", name="New Journal").click()

    def should_have_journal_selected(self, journal_title: str) -> None:
        checked_radio = self._page.locator('input[type="radio"][name="journal"]:checked')
        expect(checked_radio).to_be_attached()
        expect(self._page.locator("text=" + journal_title)).to_be_visible()

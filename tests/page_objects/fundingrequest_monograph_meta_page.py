from django.urls import reverse
from playwright.sync_api import Page, expect


class FundingRequestMonographMetaPage:
    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url

    def navigate(self, funding_request_id: int) -> None:
        url = f"{self._base_url}{reverse('fundingrequests:update_monograph_meta', args=[funding_request_id])}"
        self._page.goto(url)

    def click_next_to_publisher_step(self) -> None:
        self._page.get_by_role("button", name="Next").click()
        self._page.locator("#publisher-search-results").wait_for()

    def search_for_publisher(self, search_term: str = "") -> None:
        self._page.locator("#publisher_name").fill(search_term)
        self._page.get_by_role("button", name="Search").click()
        self._page.locator("#publisher-search-results").wait_for()

    def click_create_new_publisher_button(self) -> None:
        self._page.get_by_role("button", name="New Publisher").click()

    def should_have_publisher_selected(self, publisher_name: str) -> None:
        checked_radio = self._page.locator('input[type="radio"][name="publisher"]:checked')
        expect(checked_radio).to_be_attached()
        expect(self._page.locator("text=" + publisher_name)).to_be_visible()

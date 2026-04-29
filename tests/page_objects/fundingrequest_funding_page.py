from django.urls import reverse
from playwright.sync_api import Page, expect


class FundingRequestFundingPage:
    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url

        self._formset = page.locator("#funding-formset")

    def navigate(self, funding_request_id: int) -> None:
        url = f"{self._base_url}{reverse('fundingrequests:update_funding', args=[funding_request_id])}"
        self._page.goto(url)

    def click_create_new_funding_organization_button(self) -> None:
        self._page.get_by_role("button", name="Create New Funding Organization").click()

    def should_have_visible_formset(self) -> None:
        expect(self._formset).to_be_visible()

    def should_have_organization_in_formset(self, organization_name: str) -> None:
        expect(self._formset).to_contain_text(organization_name)

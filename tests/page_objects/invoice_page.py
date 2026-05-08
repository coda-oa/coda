from django.urls import reverse
from playwright.sync_api import Page, expect

from coda.apps.invoices.models import Creditor


class InvoiceCreationPage:
    def __init__(self, page: Page, base_url: str):
        self._page = page
        self._base_url = base_url

    def navigate(self) -> None:
        self._page.goto(f"{self._base_url}{reverse('invoices:create')}")

    # Creditor section actions
    def click_new_creditor_button(self) -> None:
        self._page.get_by_role("button", name="New").click()

    def should_have_creditor_in_select(self, name: str) -> None:
        expect(self._page.locator("#creditor-select-wrapper")).to_contain_text(name)

    def should_have_creditor_selected(self, creditor: Creditor) -> None:
        """Assert that a specific creditor is selected in the dropdown."""
        selected_option = self._page.locator("#creditor-select-wrapper").locator(
            f'li[value="{creditor.pk}"][selected]'
        )
        expect(selected_option).to_have_attribute("selected", "")
        expect(selected_option).to_contain_text(creditor.name)

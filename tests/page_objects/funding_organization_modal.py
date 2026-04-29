from playwright.sync_api import Page, expect


class FundingOrganizationModal:
    def __init__(self, page: Page):
        self._page = page
        self._modal = page.locator("#entity-creation-modal")

    # Visibility checks
    def should_be_visible(self) -> None:
        expect(self._modal).to_be_visible()

    def should_not_be_visible(self) -> None:
        expect(self._modal).not_to_be_visible()

    # Element checks
    def should_have_title(self, expected_title: str) -> None:
        expect(self._modal.locator("h2")).to_have_text(expected_title)

    def should_have_name_input(self) -> None:
        expect(self._modal.locator('input[name="name"]')).to_be_visible()

    def should_have_cancel_button(self) -> None:
        expect(self._modal.get_by_role("button", name="Cancel")).to_be_visible()

    def should_have_create_button(self) -> None:
        expect(self._modal.get_by_role("button", name="Create")).to_be_visible()

    # Actions
    def fill_name(self, name: str) -> None:
        self._modal.locator('input[name="name"]').fill(name)

    def click_create_button(self) -> None:
        self._modal.get_by_role("button", name="Create").click()

    def click_cancel_button(self) -> None:
        self._modal.get_by_role("button", name="Cancel").click()

    def click_close_button(self) -> None:
        self._modal.get_by_role("button", name="Close").click()

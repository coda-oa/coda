from playwright.sync_api import Page, expect


class JournalModal:
    def __init__(self, page: Page):
        self._page = page
        self._modal = page.locator("#entity-creation-modal")

    def should_be_visible(self) -> None:
        expect(self._modal).to_be_visible()

    def should_not_be_visible(self) -> None:
        expect(self._modal).not_to_be_visible()

    def should_have_title(self, title: str = "Create New Journal") -> None:
        expect(self._modal.locator("h2")).to_have_text(title)

    def should_have_title_input(self) -> None:
        expect(self._modal.locator("#id_title")).to_be_visible()

    def should_have_eissn_input(self) -> None:
        expect(self._modal.locator("#id_eissn")).to_be_visible()

    def should_have_publisher_select(self) -> None:
        expect(self._modal.locator("#id_publisher")).to_be_visible()

    def should_have_cancel_button(self) -> None:
        expect(self._modal.get_by_role("button", name="Cancel")).to_be_visible()

    def should_have_create_button(self) -> None:
        expect(self._modal.get_by_role("button", name="Create")).to_be_visible()

    def fill_title(self, title: str) -> None:
        self._modal.locator("#id_title").fill(title)

    def fill_eissn(self, eissn: str) -> None:
        self._modal.locator("#id_eissn").fill(eissn)

    def select_publisher(self, publisher_id: int) -> None:
        self._modal.locator("#id_publisher").select_option(str(publisher_id))

    def click_create_button(self) -> None:
        self._modal.get_by_role("button", name="Create").click()

    def click_cancel_button(self) -> None:
        self._modal.get_by_role("button", name="Cancel").click()

    def click_close_button(self) -> None:
        self._modal.locator('button[aria-label="Close"]').click()

    def should_show_validation_error(self, field_name: str) -> None:
        field_id = f"id_{field_name}"
        field = self._modal.locator(f"#{field_id}")
        expect(field).to_have_attribute("aria-invalid", "true")

from playwright.sync_api import expect

from tests.page_objects.entity_creation_modal import EntityCreationModal


class JournalModal(EntityCreationModal):

    # Journal-specific field checks
    def should_have_title_input(self) -> None:
        expect(self._modal.locator("#id_title")).to_be_visible()

    def should_have_eissn_input(self) -> None:
        expect(self._modal.locator("#id_eissn")).to_be_visible()

    def should_have_publisher_select(self) -> None:
        expect(self._modal.locator("#id_publisher")).to_be_visible()

    # Journal-specific actions
    def fill_title(self, title: str) -> None:
        self._modal.locator("#id_title").fill(title)

    def fill_eissn(self, eissn: str) -> None:
        self._modal.locator("#id_eissn").fill(eissn)

    def select_publisher(self, publisher_id: int) -> None:
        self._modal.locator("#id_publisher").select_option(str(publisher_id))

    def should_show_validation_error(self, field_name: str) -> None:
        field_id = f"id_{field_name}"
        field = self._modal.locator(f"#{field_id}")
        expect(field).to_have_attribute("aria-invalid", "true")

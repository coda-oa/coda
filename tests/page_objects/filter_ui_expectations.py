import re

from playwright.sync_api import Locator, Page, expect

from tests.page_objects import filter_ui_selectors


def expect_text(locator: Locator, text: str) -> None:
    expect(locator).to_contain_text(text)


def expect_text_before(locator: Locator, first: str, second: str) -> None:
    pattern = re.compile(rf".*{re.escape(first)}.*{re.escape(second)}.*", re.DOTALL)
    expect(locator).to_have_text(pattern)


def expect_no_text(locator: Locator, text: str) -> None:
    expect(locator).not_to_contain_text(text)


def expect_active_filter(page: Page, name: str) -> None:
    filter_chip = page.locator(filter_ui_selectors.ACTIVE_FILTERS).locator(
        filter_ui_selectors.ACTIVE_FILTER
    )
    expect(filter_chip.filter(has_text=name).first).to_be_visible()


def expect_active_filter_count(page: Page, count: int) -> None:
    filter_chips = page.locator(filter_ui_selectors.ACTIVE_FILTERS).locator(
        filter_ui_selectors.ACTIVE_FILTER
    )
    expect(filter_chips).to_have_count(count)


def expect_filter_count(page: Page, count: int) -> None:
    expect(page.locator(filter_ui_selectors.FILTER_COUNT_BADGE)).to_have_text(str(count))


def expect_clear_all(page: Page) -> None:
    expect(page.locator(filter_ui_selectors.FILTER_CLEAR_ALL)).to_have_text("Clear all")


def expect_url_query(page: Page, fragment: str) -> None:
    expect(page).to_have_url(re.compile(re.escape(fragment)))


def expect_no_url_query(page: Page, fragment: str) -> None:
    expect(page).not_to_have_url(re.compile(re.escape(fragment)))


def expect_control_value(page: Page, selector: str, value: str) -> None:
    page.wait_for_function(
        """([selector, expected]) => {
            const element = document.querySelector(selector);
            return element !== null && element.value === expected;
        }""",
        arg=[selector, value],
    )


def expect_checked_control(page: Page, selector: str) -> None:
    expect(page.locator(selector)).to_be_checked()


def expect_unchecked_control(page: Page, selector: str) -> None:
    expect(page.locator(selector)).not_to_be_checked()


def expect_no_selected_options(page: Page, selector: str) -> None:
    expect(page.locator(selector).locator(filter_ui_selectors.SELECTED_TAG)).to_have_count(0)


def expect_selected_options(page: Page, selector: str, texts: list[str]) -> None:
    tags = page.locator(selector).locator(filter_ui_selectors.SELECTED_TAG)
    expect(tags).to_have_count(len(texts))
    for text in texts:
        expect(tags.filter(has_text=text).first).to_be_visible()

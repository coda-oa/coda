"""UI tests for the vocabulary editor's htmx swap behavior.

Every response that swaps `#vocabulary-table` (move-to-forbidden / move-to-allowed)
carries the `concept-ui-init` client event with ``after="swap"``. The swapped-in
table replaces the filter inputs, the move buttons, and all checkboxes, so the
JS wiring must run *after* the swap. With the default ``after="receive"`` the
event fires before the swap: the handlers bind to the soon-to-be-detached nodes
and the freshly rendered table stays dead.

These tests assert observable behavior of the *new* DOM after a swap; they fail
when the event fires at receive time.
"""

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.vocabulary import Vocabulary

ALLOWED_ALPHA = 'input[name="allowed_concepts_check"][value="A"]'
FORBIDDEN_ALPHA = 'input[name="disallowed_concepts_check"][value="A"]'


def _create_base_vocabulary() -> Vocabulary:
    vocabulary = Vocabulary(id=None, name="UI Base Vocabulary", version="1.0")
    vocabulary.add_concept("A", name="Alpha Concept")
    vocabulary.add_concept("B", name="Beta Concept")
    vocabulary_repository.save(vocabulary)
    return vocabulary


def _open_editor(page: Page, live_server: LiveServer, base: Vocabulary) -> None:
    page.goto(
        live_server.url + reverse("publications:vocabulary_create_limited", kwargs={"pk": base.id})
    )


def _move_alpha_to_forbidden(page: Page) -> None:
    page.locator(ALLOWED_ALPHA).check()
    page.locator("#disallow-button").click()
    expect(page.locator(FORBIDDEN_ALPHA)).to_be_visible()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__move_concept_to_forbidden__rewired_select_all_button__checks_swapped_in_checkboxes(
    coda_page: Page, live_server: LiveServer
) -> None:
    base = _create_base_vocabulary()
    _open_editor(coda_page, live_server, base)
    _move_alpha_to_forbidden(coda_page)

    coda_page.locator("#select-all-forbidden").click()

    expect(coda_page.locator(FORBIDDEN_ALPHA)).to_be_checked()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__move_concept_to_forbidden__rewired_filter__hides_non_matching_allowed_concepts(
    coda_page: Page, live_server: LiveServer
) -> None:
    base = _create_base_vocabulary()
    _open_editor(coda_page, live_server, base)
    _move_alpha_to_forbidden(coda_page)

    beta_row = coda_page.locator("#allowed-checkboxes li", has_text="Beta Concept")
    expect(beta_row).to_be_visible()

    coda_page.fill("#allowed-filter", "Alpha")

    expect(beta_row).to_be_hidden()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__move_concept_to_forbidden__rewired_toggle_state__disallow_button_disabled_without_selection(
    coda_page: Page, live_server: LiveServer
) -> None:
    base = _create_base_vocabulary()
    _open_editor(coda_page, live_server, base)
    _move_alpha_to_forbidden(coda_page)

    expect(coda_page.locator("#disallow-button")).to_be_disabled()

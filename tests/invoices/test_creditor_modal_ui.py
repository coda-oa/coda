import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.invoices.models import Creditor
from tests.page_objects.creditor_modal import CreditorModal
from tests.page_objects.invoice_page import InvoiceCreationPage


@pytest.mark.ui_test
@pytest.mark.django_db
def test__invoice_create_page__click_new_creditor_button__modal_opens_with_form(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    _, modal = navigate_to_invoice_creation_page_and_open_creditor_modal(coda_page, live_server)

    modal.should_be_visible()
    modal.should_have_title("Create New Creditor")
    modal.should_have_name_input()
    modal.should_have_cancel_button()
    modal.should_have_create_button()


@pytest.mark.ui_test
@pytest.mark.django_db
def test__invoice_create_page__create_valid_creditor_in_modal__modal_closes_and_creditor_appears_in_select_and_is_selected(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    creditor_name = "Acme Corporation"

    invoice_page, modal = navigate_to_invoice_creation_page_and_open_creditor_modal(
        coda_page, live_server
    )

    modal.should_be_visible()
    modal.fill_name(creditor_name)
    modal.click_create_button()

    modal.should_not_be_visible()
    assert Creditor.objects.filter(name=creditor_name).exists()
    creditor = Creditor.objects.get(name=creditor_name)
    invoice_page.should_have_creditor_in_select(creditor_name)
    invoice_page.should_have_creditor_selected(creditor)


@pytest.mark.ui_test
@pytest.mark.django_db
def test__invoice_create_page__click_cancel_button__modal_closes_without_creating_creditor(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    initial_count = Creditor.objects.count()
    _, modal = navigate_to_invoice_creation_page_and_open_creditor_modal(coda_page, live_server)
    modal.should_be_visible()

    modal.fill_name("Test Creditor")
    modal.click_cancel_button()

    modal.should_not_be_visible()
    assert Creditor.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db
def test__invoice_creation_page__submit_empty_form_in_creditor_modal__keeps_modal_open_and_does_not_create_new_creditor(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    initial_count = Creditor.objects.count()
    _, modal = navigate_to_invoice_creation_page_and_open_creditor_modal(coda_page, live_server)

    # Click Create without filling the form
    modal.click_create_button()

    modal.should_be_visible()
    assert Creditor.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db
def test__invoice_creation_page__click_close_button__modal_closes_without_creating_creditor(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    initial_count = Creditor.objects.count()
    _, modal = navigate_to_invoice_creation_page_and_open_creditor_modal(coda_page, live_server)

    modal.click_close_button()

    modal.should_not_be_visible()
    assert Creditor.objects.count() == initial_count


def navigate_to_invoice_creation_page_and_open_creditor_modal(
    coda_page: Page, live_server: LiveServer
) -> tuple[InvoiceCreationPage, CreditorModal]:
    invoice_page = InvoiceCreationPage(coda_page, live_server.url)
    invoice_page.navigate()
    invoice_page.click_new_creditor_button()
    modal = CreditorModal(coda_page)
    return invoice_page, modal

import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests.models import FundingOrganization, FundingRequest
from coda.apps.publications.models import LinkType
from tests import modelfactory
from tests.page_objects.funding_organization_modal import FundingOrganizationModal
from tests.page_objects.fundingrequest_funding_page import FundingRequestFundingPage


def _create_test_funding_request() -> FundingRequest:
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")

    return modelfactory.fundingrequest()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__open_funding_organization_modal__displays_correct_form(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()

    _, modal = navigate_to_funding_section_and_open_modal(coda_page, live_server, funding_request)

    modal.should_be_visible()
    modal.should_have_title("Create New Funding Organization")
    modal.should_have_name_input()
    modal.should_have_cancel_button()
    modal.should_have_create_button()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__create_valid_funding_organization__modal_closes_and_formset_updates(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()
    organization_name = "German Research Foundation"

    funding_page, modal = navigate_to_funding_section_and_open_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()

    modal.fill_name(organization_name)
    modal.click_create_button()

    modal.should_not_be_visible()
    assert FundingOrganization.objects.filter(name=organization_name).exists()
    funding_page.should_have_organization_in_formset(organization_name)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__submit_empty_form__shows_validation_and_keeps_modal_open(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()
    initial_count = FundingOrganization.objects.count()
    _, modal = navigate_to_funding_section_and_open_modal(coda_page, live_server, funding_request)
    modal.should_be_visible()

    # Click Create without filling the form
    modal.click_create_button()

    modal.should_be_visible()
    assert FundingOrganization.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__create_organization_with_existing_formset_data__both_existing_and_new_appear_in_formset(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()
    existing_org = FundingOrganization.objects.create(name="Existing Foundation")
    new_organization_name = "European Research Council"
    funding_page, modal = navigate_to_funding_section_and_open_modal(
        coda_page, live_server, funding_request
    )
    funding_page.should_have_visible_formset()
    modal.should_be_visible()

    modal.fill_name(new_organization_name)
    modal.click_create_button()

    modal.should_not_be_visible()
    assert FundingOrganization.objects.filter(name=new_organization_name).exists()
    funding_page.should_have_organization_in_formset(existing_org.name)
    funding_page.should_have_organization_in_formset(new_organization_name)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__create_organization_with_multiple_existing_orgs__all_appear_in_formset(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()
    org1 = FundingOrganization.objects.create(name="Foundation One")
    org2 = FundingOrganization.objects.create(name="Foundation Two")
    new_org_name = "Swiss National Science Foundation"

    funding_page, modal = navigate_to_funding_section_and_open_modal(
        coda_page, live_server, funding_request
    )
    funding_page.should_have_visible_formset()
    modal.should_be_visible()

    modal.fill_name(new_org_name)
    modal.click_create_button()

    modal.should_not_be_visible()
    assert FundingOrganization.objects.filter(name=new_org_name).exists()
    funding_page.should_have_organization_in_formset(org1.name)
    funding_page.should_have_organization_in_formset(org2.name)
    funding_page.should_have_organization_in_formset(new_org_name)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__click_cancel_button_in_funding_org_modal__modal_closes_without_creating_organization(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()
    initial_count = FundingOrganization.objects.count()
    _, modal = navigate_to_funding_section_and_open_modal(coda_page, live_server, funding_request)
    modal.should_be_visible()

    modal.fill_name("Test Organization")
    modal.click_cancel_button()

    modal.should_not_be_visible()
    assert FundingOrganization.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__fundingrequest_funding_section__click_close_button_in_funding_org_modal__modal_closes_without_creating_organization(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_funding_request()
    initial_count = FundingOrganization.objects.count()
    _, modal = navigate_to_funding_section_and_open_modal(coda_page, live_server, funding_request)
    modal.should_be_visible()

    modal.fill_name("Test Organization")
    modal.click_close_button()

    modal.should_not_be_visible()
    assert FundingOrganization.objects.count() == initial_count


def navigate_to_funding_section_and_open_modal(
    coda_page: Page, live_server: LiveServer, funding_request: FundingRequest
) -> tuple[FundingRequestFundingPage, FundingOrganizationModal]:
    funding_page = FundingRequestFundingPage(coda_page, live_server.url)
    funding_page.navigate(funding_request.pk)
    funding_page.click_create_new_funding_organization_button()

    modal = FundingOrganizationModal(coda_page)
    return funding_page, modal

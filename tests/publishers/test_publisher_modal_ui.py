import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publishers.models import Publisher
from coda.apps.publications.models import LinkType
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest
from tests import domainfactory, modelfactory
from tests.page_objects.fundingrequest_monograph_meta_page import FundingRequestMonographMetaPage
from tests.page_objects.publisher_modal import PublisherModal


def _create_test_monograph_funding_request() -> FundingRequestModel:
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")

    publisher = modelfactory.publisher()
    monograph = domainfactory.monograph(publisher=PublisherId(publisher.pk))

    request_id = repository.create(FundingRequest.new(monograph, domainfactory.payment()))

    return FundingRequestModel.objects.get(pk=request_id)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__monograph_meta__open_publisher_modal__displays_correct_form(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_monograph_funding_request()

    _, modal = navigate_to_monograph_meta_and_open_publisher_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.should_have_title("Create New Publisher")
    modal.should_have_name_input()
    modal.should_have_cancel_button()
    modal.should_have_create_button()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__monograph_meta__create_valid_publisher__modal_closes_and_publisher_selected(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_monograph_funding_request()
    publisher_name = "Penguin Books"

    monograph_page, modal = navigate_to_monograph_meta_and_open_publisher_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.fill_name(publisher_name)
    modal.click_create_button()

    modal.should_not_be_visible()
    assert Publisher.objects.filter(name=publisher_name).exists()
    monograph_page.should_have_publisher_selected(publisher_name)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__monograph_meta__submit_empty_form__shows_validation_and_keeps_modal_open(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_monograph_funding_request()
    initial_count = Publisher.objects.count()

    _, modal = navigate_to_monograph_meta_and_open_publisher_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.click_create_button()

    modal.should_be_visible()
    assert Publisher.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__monograph_meta__click_cancel_button__modal_closes_without_creating_publisher(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_monograph_funding_request()
    initial_count = Publisher.objects.count()

    _, modal = navigate_to_monograph_meta_and_open_publisher_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.fill_name("Test Publisher")
    modal.click_cancel_button()

    modal.should_not_be_visible()
    assert Publisher.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__monograph_meta__click_close_button__modal_closes_without_creating_publisher(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_monograph_funding_request()
    initial_count = Publisher.objects.count()

    _, modal = navigate_to_monograph_meta_and_open_publisher_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.fill_name("Test Publisher")
    modal.click_close_button()

    modal.should_not_be_visible()
    assert Publisher.objects.count() == initial_count


def navigate_to_monograph_meta_and_open_publisher_modal(
    coda_page: Page, live_server: LiveServer, funding_request: FundingRequestModel
) -> tuple[FundingRequestMonographMetaPage, PublisherModal]:
    monograph_page = FundingRequestMonographMetaPage(coda_page, live_server.url)
    monograph_page.navigate(funding_request.pk)

    monograph_page.click_next_to_publisher_step()

    monograph_page.search_for_publisher("")

    monograph_page.click_create_new_publisher_button()

    modal = PublisherModal(coda_page)
    return monograph_page, modal

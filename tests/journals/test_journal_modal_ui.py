import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.apps.publications.models import LinkType
from tests import domainfactory, modelfactory
from tests.page_objects.fundingrequest_article_meta_page import FundingRequestArticleMetaPage
from tests.page_objects.journal_modal import JournalModal
from coda.apps.fundingrequests import repository
from coda.domain.fundingrequest import FundingRequest
from coda.domain.publication import JournalId


def _create_test_article_funding_request() -> FundingRequestModel:
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")

    journal = modelfactory.journal()

    article = domainfactory.publication(journal=JournalId(journal.pk))

    funding_request_id = repository.create(FundingRequest.new(article, domainfactory.payment()))

    return FundingRequestModel.objects.get(pk=funding_request_id)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__article_meta__open_journal_modal__displays_correct_form(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_article_funding_request()

    _, modal = navigate_to_article_meta_and_open_journal_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.should_have_title("Create New Journal")
    modal.should_have_title_input()
    modal.should_have_eissn_input()
    modal.should_have_publisher_select()
    modal.should_have_cancel_button()
    modal.should_have_create_button()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__article_meta__create_valid_journal__modal_closes_and_journal_selected(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_article_funding_request()
    publisher = Publisher.objects.create(name="Test Publisher")
    journal_title = "Nature"
    eissn = "1476-4687"

    article_page, modal = navigate_to_article_meta_and_open_journal_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.fill_title(journal_title)
    modal.fill_eissn(eissn)
    modal.select_publisher(publisher.pk)
    modal.click_create_button()

    modal.should_not_be_visible()
    assert Journal.objects.filter(title=journal_title, eissn=eissn).exists()
    article_page.should_have_journal_selected(journal_title)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__article_meta__submit_empty_form__shows_validation_and_keeps_modal_open(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_article_funding_request()
    initial_count = Journal.objects.count()

    _, modal = navigate_to_article_meta_and_open_journal_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.click_create_button()

    modal.should_be_visible()
    assert Journal.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__article_meta__click_cancel_button__modal_closes_without_creating_journal(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_article_funding_request()
    publisher = Publisher.objects.create(name="Test Publisher")
    initial_count = Journal.objects.count()

    _, modal = navigate_to_article_meta_and_open_journal_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.fill_title("Test Journal")
    modal.fill_eissn("1234-5678")
    modal.select_publisher(publisher.pk)
    modal.click_cancel_button()

    modal.should_not_be_visible()
    assert Journal.objects.count() == initial_count


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__article_meta__click_close_button__modal_closes_without_creating_journal(
    coda_page: Page,
    live_server: LiveServer,
) -> None:
    funding_request = _create_test_article_funding_request()
    publisher = Publisher.objects.create(name="Test Publisher")
    initial_count = Journal.objects.count()

    _, modal = navigate_to_article_meta_and_open_journal_modal(
        coda_page, live_server, funding_request
    )

    modal.should_be_visible()
    modal.fill_title("Test Journal")
    modal.fill_eissn("1234-5678")
    modal.select_publisher(publisher.pk)
    modal.click_close_button()

    modal.should_not_be_visible()
    assert Journal.objects.count() == initial_count


def navigate_to_article_meta_and_open_journal_modal(
    coda_page: Page, live_server: LiveServer, funding_request: FundingRequestModel
) -> tuple[FundingRequestArticleMetaPage, JournalModal]:
    article_page = FundingRequestArticleMetaPage(coda_page, live_server.url)
    article_page.navigate(funding_request.pk)

    # Click "Next" to proceed to step 2 (journal selection)
    article_page.click_next_to_journal_step()

    # Search for journal (empty search to show "no results" with "New Journal" button)
    article_page.search_for_journal("")

    article_page.click_create_new_journal_button()

    modal = JournalModal(coda_page)
    return article_page, modal

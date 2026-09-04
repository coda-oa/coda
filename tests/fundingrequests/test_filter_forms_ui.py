from django.urls import reverse
import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.models import LinkType
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest
from tests import domainfactory, modelfactory


def _create_article_and_monograph_titles() -> tuple[str, str]:
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")

    article = modelfactory.fundingrequest(title="E2E filter article")
    monograph_request_id = repository.create(
        FundingRequest.new(
            domainfactory.monograph(publisher=PublisherId(modelfactory.publisher().pk)),
            domainfactory.payment(),
        )
    )
    monograph = FundingRequestModel.objects.get(pk=monograph_request_id)

    return str(article.publication.title), str(monograph.publication.title)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__filter_forms__values_are_sent_with_region_updates(coda_page: Page, live_server: LiveServer) -> None:
    article_title, monograph_title = _create_article_and_monograph_titles()

    coda_page.set_viewport_size({"width": 1440, "height": 900})
    coda_page.goto(live_server.url + reverse("fundingrequests:list"))
    coda_page.wait_for_function("() => typeof htmx !== 'undefined'")

    assert article_title in coda_page.inner_text("#fundingrequest-list")
    assert monograph_title in coda_page.inner_text("#fundingrequest-list")

    coda_page.click('label[for="publication_type_article"]')
    coda_page.wait_for_function(
        "(title) => !document.querySelector('#fundingrequest-list')?.textContent?.includes(title)",
        arg=monograph_title,
    )
    assert article_title in coda_page.inner_text("#fundingrequest-list")
    assert "publication_type=article" in coda_page.url

    coda_page.type(".filter-search", "zzz-no-such-title", delay=50)
    coda_page.wait_for_function(
        "() => document.querySelector('#fundingrequest-list')?.textContent"
        "?.includes('No funding requests match')"
    )
    assert article_title not in coda_page.inner_text("#fundingrequest-list")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__filter_forms__keep_label_filter_set_by_pills(coda_page: Page, live_server: LiveServer) -> None:
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")

    label = label_create("E2E State", Color.from_rgb(0, 128, 0))
    labeled = modelfactory.fundingrequest(title="E2E state labeled")
    label_attach(labeled, label)
    unlabeled = modelfactory.fundingrequest(title="E2E state unlabeled")
    labeled_title = str(labeled.publication.title)
    unlabeled_title = str(unlabeled.publication.title)

    coda_page.set_viewport_size({"width": 1440, "height": 900})
    coda_page.goto(live_server.url + reverse("fundingrequests:list"))
    coda_page.wait_for_function("() => typeof htmx !== 'undefined'")

    assert labeled_title in coda_page.inner_text("#fundingrequest-list")
    assert unlabeled_title in coda_page.inner_text("#fundingrequest-list")

    coda_page.click(".label-filter-pill:has-text('E2E State')")
    coda_page.wait_for_function(
        "(title) => !document.querySelector('#fundingrequest-list')?.textContent?.includes(title)",
        arg=unlabeled_title,
    )

    coda_page.click('label[for="publication_type_article"]')
    coda_page.wait_for_function("() => location.search.includes('publication_type=article')")

    region_text = coda_page.inner_text("#fundingrequest-list")
    assert labeled_title in region_text
    assert unlabeled_title not in region_text
    assert f"labels={label.pk}" in coda_page.url

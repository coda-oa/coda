from django.urls import reverse
import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.publications.models import LinkType
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from tests import modelfactory


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__label_pill__click_updates_list_in_place(coda_page: Page, live_server: LiveServer) -> None:
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")

    alpha = label_create("E2E Alpha", Color.from_rgb(255, 0, 0))
    matching = modelfactory.fundingrequest(title="E2E pill match")
    label_attach(matching, alpha)
    modelfactory.fundingrequest(title="E2E pill non-match")

    coda_page.set_viewport_size({"width": 1440, "height": 900})
    coda_page.goto(live_server.url + reverse("fundingrequests:list"))
    coda_page.wait_for_function("() => typeof htmx !== 'undefined'")

    assert "E2E pill match" in coda_page.inner_text("#fundingrequest-list")
    assert "E2E pill non-match" in coda_page.inner_text("#fundingrequest-list")

    coda_page.click(".label-filter-pill:has-text('E2E Alpha')")
    coda_page.wait_for_function(
        "() => !document.querySelector('#fundingrequest-list')?.textContent"
        "?.includes('E2E pill non-match')"
    )

    region_text = coda_page.inner_text("#fundingrequest-list")
    assert "E2E pill match" in region_text
    assert "E2E pill non-match" not in region_text

    assert "Clear all" in coda_page.inner_text("#filter-sidebar-header")
    assert "labels=" in coda_page.url

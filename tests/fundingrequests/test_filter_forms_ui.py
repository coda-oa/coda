from datetime import date

import pytest
from playwright.sync_api import Page
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest
from tests import domainfactory, modelfactory
from tests.page_objects.fundingrequest_list_page import FundingRequestListPage


def _create_article_and_monograph_titles() -> tuple[str, str]:
    article = modelfactory.fundingrequest(title="E2E filter article")
    monograph_request_id = repository.create(
        FundingRequest.new(
            domainfactory.monograph(publisher=PublisherId(modelfactory.publisher().pk)),
            domainfactory.payment(),
        )
    )
    monograph = FundingRequestModel.objects.get(pk=monograph_request_id)

    return article.publication.title, monograph.publication.title


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__filter_forms__values_are_sent_with_region_updates(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    article_title, monograph_title = _create_article_and_monograph_titles()
    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    list_page.should_show_request(article_title)
    list_page.should_show_request(monograph_title)

    list_page.select_publication_type("article")
    list_page.should_not_show_request(monograph_title)
    list_page.should_show_request(article_title)
    list_page.should_have_url_query("publication_type=article")

    list_page.type_search("zzz-no-such-title")
    list_page.should_show_empty_state()
    list_page.should_not_show_request(article_title)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__filter_forms__keep_label_filter_set_by_pills(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    label = label_create("E2E State", Color.from_rgb(0, 128, 0))
    labeled = modelfactory.fundingrequest(title="E2E state labeled")
    label_attach(labeled, label)
    unlabeled = modelfactory.fundingrequest(title="E2E state unlabeled")
    labeled_title = labeled.publication.title
    unlabeled_title = unlabeled.publication.title

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    list_page.should_show_request(labeled_title)
    list_page.should_show_request(unlabeled_title)

    list_page.click_label_pill("E2E State")
    list_page.should_not_show_request(unlabeled_title)

    list_page.select_publication_type("article")
    list_page.should_have_url_query("publication_type=article")

    list_page.should_show_request(labeled_title)
    list_page.should_not_show_request(unlabeled_title)
    list_page.should_have_url_query(f"labels={label.pk}")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__active_filter_chips__summary_shows_and_removes_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    alpha = label_create("Alpha chip", Color.from_rgb(255, 0, 0))
    beta = label_create("Beta chip", Color.from_rgb(0, 0, 255))
    label_attach(modelfactory.fundingrequest(title="Alpha chip paper"), alpha)
    label_attach(modelfactory.fundingrequest(title="Beta chip paper"), beta)

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.click_label_pill("Alpha chip")
    list_page.click_label_pill("Beta chip")

    list_page.should_show_active_filter("Alpha chip")
    list_page.should_show_active_filter("Beta chip")
    list_page.should_have_filter_count(2)
    list_page.should_show_request("Alpha chip paper")

    list_page.remove_active_filter("Alpha chip")
    list_page.should_not_show_request("Alpha chip paper")

    list_page.should_have_active_filter_count(1)
    list_page.should_show_request("Beta chip paper")
    list_page.should_not_show_request("Alpha chip paper")
    list_page.should_have_url_query(f"labels={beta.pk}")
    list_page.should_not_have_url_query(f"labels={alpha.pk}")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__chip_removal__resets_sidebar_controls(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    contract = modelfactory.contract()

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()
    list_page.filter_by_processing_status("approved")
    list_page.filter_by_payment_status("paid")
    list_page.select_publication_type("article")
    list_page.choose_contract(contract.name)
    list_page.show_only_invalid_contract_years()

    chip_names = ("approved", "Paid", "Article", contract.name, "Invalid years only")
    for name in chip_names:
        list_page.should_show_active_filter(name)
    for name in chip_names:
        list_page.remove_active_filter(name)

    list_page.should_have_no_selected_options("#processing_status")
    list_page.should_have_no_selected_options("#id_payment_status")
    list_page.should_be_checked("#publication_type_all")
    list_page.should_have_unchecked_control("#publication_type_article")
    list_page.should_have_form_value("#contract_name", "")
    list_page.should_have_unchecked_control("#invalid_contract_years")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__sort_change__reorders_list_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    alpha = modelfactory.fundingrequest(title="AA-alpha request")
    zulu = modelfactory.fundingrequest(title="ZZ-zulu request")
    FundingRequestModel.objects.filter(pk=alpha.pk).update(request_date=date(2024, 1, 1))
    FundingRequestModel.objects.filter(pk=zulu.pk).update(request_date=date(2024, 6, 1))

    list_page = FundingRequestListPage(coda_page, live_server.url)
    list_page.navigate()

    list_page.should_show_request_before("ZZ-zulu request", "AA-alpha request")

    list_page.sort_by("alphabetical")

    list_page.should_show_request_before("AA-alpha request", "ZZ-zulu request")
    list_page.should_have_url_query("sort_by=alphabetical")

import re
from urllib.parse import urlsplit

import pytest
from django.http import QueryDict
from django.test import Client, RequestFactory
from django.test.html import parse_html
from django.urls import reverse

from coda.apps.fundingrequests.views.listview import label_pill_url
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from tests import modelfactory
from tests.filterdom import hidden_values


def test__label_pill_url__preserves_other_get_params_and_sets_labels_sorted() -> None:
    request = RequestFactory().get(
        "/fundingrequests/list/?search_term=foo&exclude_labels=3&sort_by=alphabetical"
    )

    url = label_pill_url(request, labels={2, 1})

    assert urlsplit(url).path == reverse("fundingrequests:list")
    params = QueryDict(urlsplit(url).query)
    assert params["search_term"] == "foo"
    assert params["exclude_labels"] == "3"
    assert params["sort_by"] == "alphabetical"
    assert params.getlist("labels") == ["1", "2"]


def test__label_pill_url__drops_page_param() -> None:
    request = RequestFactory().get("/fundingrequests/list/?labels=1&page=3")

    url = label_pill_url(request, labels={1, 2})

    params = QueryDict(urlsplit(url).query)
    assert "page" not in params
    assert params.getlist("labels") == ["1", "2"]


def test__label_pill_url__empty_label_list__yields_bare_list_url() -> None:
    request = RequestFactory().get("/fundingrequests/list/?labels=1&page=2")

    assert label_pill_url(request, labels=set()) == reverse("fundingrequests:list")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__label_pills__render_state_and_toggle_url_per_label(client: Client) -> None:
    alpha = label_create("Alpha", Color.from_rgb(255, 0, 0))
    beta = label_create("Beta", Color.from_rgb(0, 0, 255))
    labeled = modelfactory.fundingrequest()
    label_attach(labeled, alpha)
    label_attach(labeled, beta)

    response = client.get(reverse("fundingrequests:list"), {"labels": [alpha.pk]})

    list_url = reverse("fundingrequests:list")
    pills = {pill.name: pill for pill in response.context["label_pills"]}
    assert pills["Alpha"].state == "included"
    assert pills["Beta"].state == "default"
    assert pills["Alpha"].toggle_url == list_url
    assert pills["Beta"].toggle_url == f"{list_url}?labels={alpha.pk}&labels={beta.pk}"

    html = response.content.decode()
    assert "label-filter-pill included" in html
    assert "label-filter-pill default" in html
    assert response.context["filter_count"] == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__labels_and_exclude_labels__filter_results_and_keep_dropdown_in_sync(
    client: Client,
) -> None:
    alpha = label_create("Alpha", Color.from_rgb(255, 0, 0))
    beta = label_create("Beta", Color.from_rgb(0, 0, 255))
    matching = modelfactory.fundingrequest()
    label_attach(matching, alpha)
    non_matching = modelfactory.fundingrequest()
    label_attach(non_matching, beta)

    response = client.get(
        reverse("fundingrequests:list"),
        {"labels": [alpha.pk], "exclude_labels": [beta.pk]},
    )

    ids = [viewmodel.id for viewmodel in response.context["entities"]]
    assert ids == [matching.id]
    assert response.context["filter_count"] == 2

    html = response.content.decode()
    assert re.search(rf'value="{beta.pk}"[^>]*selected', html)
    assert not re.search(rf'value="{alpha.pk}"[^>]*selected', html)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__label_filter__only_offers_labels_used_by_requests(client: Client) -> None:
    """An unused label gets no pill, no option, and selects nothing via the URL."""
    unused = label_create("Unused", Color.from_rgb(128, 128, 128))
    used = label_create("Used", Color.from_rgb(255, 0, 0))
    labeled = modelfactory.fundingrequest(title="Used label paper")
    label_attach(labeled, used)

    response = client.get(reverse("fundingrequests:list"))

    assert [pill.name for pill in response.context["label_pills"]] == ["Used"]
    html = response.content.decode()
    assert f'value="{used.pk}"' in html
    assert f'value="{unused.pk}"' not in html

    filtered = client.get(reverse("fundingrequests:list"), {"labels": [unused.pk]})

    assert [pill.name for pill in filtered.context["label_pills"]] == ["Used"]
    assert filtered.context["filter_count"] == 0
    ids = [viewmodel.id for viewmodel in filtered.context["entities"]]
    assert ids == [labeled.id]
    assert hidden_values(parse_html(filtered.content.decode()), "labels") == []


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize("param", ["labels", "exclude_labels"])
def test__bad_label_param__is_ignored_instead_of_500(client: Client, param: str) -> None:
    response = client.get(reverse("fundingrequests:list"), {param: "abc"})

    assert response.status_code == 200

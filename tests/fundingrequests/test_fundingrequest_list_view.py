from datetime import date
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import Element, parse_html
from django.urls import reverse

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.fundingrequest.review import ReviewResult
from tests import modelfactory
from tests.filterdom import (
    checked_radio_values,
    clear_all_text,
    hidden_values,
    rendered_field_names,
    selected_values,
    walk,
)


def goto_list_page(
    client: Client,
    query: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))


def get_list_region(
    client: Client,
    query: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list_region"), data=query))


def pill_elements(dom: Element) -> list[Element]:
    return [
        element
        for element in walk(dom)
        if element.name == "a"
        and "label-filter-pill" in (dict(element.attributes).get("class") or "")
    ]


def pill_by_name(dom: Element, name: str) -> Element:
    for element in walk(dom):
        if element.name != "a":
            continue
        attrs = dict(element.attributes)
        text = "".join(child for child in element.children if isinstance(child, str)).strip()
        if "label-filter-pill" in (attrs.get("class") or "") and text == name:
            return element
    raise AssertionError(f"no label pill named {name!r} in page")


def pill_state(dom: Element, name: str) -> str:
    classes = (dict(pill_by_name(dom, name).attributes).get("class") or "").split()
    for state in ("included", "default"):
        if state in classes:
            return state
    raise AssertionError(f"label pill {name!r} has no state class")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__label_pill__link_points_at_filtered_list(client: Client) -> None:
    label_create("Pill A", Color())

    response = goto_list_page(client)
    pills = pill_elements(parse_html(response.content.decode()))

    assert pills, "no label pills rendered on the list page"
    for pill in pills:
        href = dict(pill.attributes).get("href") or ""
        assert href.startswith(reverse("fundingrequests:list"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__label_filter__list_shows_only_requests_with_label(client: Client) -> None:
    alpha = label_create("Alpha", Color.from_rgb(255, 0, 0))
    beta = label_create("Beta", Color.from_rgb(0, 0, 255))
    matching = modelfactory.fundingrequest(title="Pill match")
    label_attach(matching, alpha)
    label_attach(matching, beta)
    modelfactory.fundingrequest(title="Pill non-match")

    response = get_list_region(client, {"labels": [alpha.pk]})

    html = response.content.decode()
    assert "Pill match" in html
    assert "Pill non-match" not in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__label_filter__pills_reflect_active_filter(client: Client) -> None:
    alpha = label_create("Alpha", Color.from_rgb(255, 0, 0))
    label_create("Beta", Color.from_rgb(0, 0, 255))

    response = get_list_region(client, {"labels": [alpha.pk]})

    dom = parse_html(response.content.decode())
    assert pill_state(dom, "Alpha") == "included"
    assert pill_state(dom, "Beta") == "default"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__is_zero_without_filters(client: Client) -> None:
    response = goto_list_page(client)

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__counts_each_selected_value(client: Client) -> None:
    label = label_create("Counted Label", Color())

    response = goto_list_page(
        client,
        {
            "processing_status": [ReviewResult.Approved.value, ReviewResult.Rejected.value],
            "labels": [label.pk],
            "publication_type": "article",
            "invalid_contract_years": "on",
        },
    )

    assert response.context["filter_count"] == 5


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__ignores_default_publication_type(client: Client) -> None:
    response = goto_list_page(client, {"publication_type": "all"})

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_processing_statuses(client: Client) -> None:
    response = goto_list_page(client, {"processing_status": ["approved", "rejected"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "processing_status") == ["approved", "rejected"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_payment_methods(client: Client) -> None:
    response = goto_list_page(client, {"payment_methods": ["direct"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "payment_methods") == ["direct"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_publication_type(client: Client) -> None:
    response = goto_list_page(client, {"publication_type": "monograph"})

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["monograph"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__defaults_publication_type_to_all(client: Client) -> None:
    response = goto_list_page(client)

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["all"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__returns_list_and_sidebar_not_toolbar(client: Client) -> None:
    modelfactory.fundingrequest(title="Region content paper")

    html = get_list_region(client).content.decode()

    assert "Region content paper" in html
    names = rendered_field_names(parse_html(html))
    assert "processing_status" in names
    assert names.isdisjoint({"search_term", "sort_by"})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__excludes_search_and_sort(client: Client) -> None:
    response = goto_list_page(client, {"search_term": "x", "sort_by": "alphabetical"})

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clear_all__shown_with_active_filters(client: Client) -> None:
    label = label_create("Counted Label", Color())
    response = get_list_region(client, {"labels": [label.pk]})

    assert clear_all_text(response.content.decode()) == "Clear all"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clear_all__hidden_without_filters(client: Client) -> None:
    response = get_list_region(client)

    assert clear_all_text(response.content.decode()) is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_page__carries_label_state_for_form_submission(client: Client) -> None:
    alpha = label_create("Alpha", Color())
    beta = label_create("Beta", Color())

    response = goto_list_page(client, {"labels": [beta.pk, alpha.pk]})

    assert hidden_values(parse_html(response.content.decode()), "labels") == [
        str(alpha.pk),
        str(beta.pk),
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__carries_label_state_for_form_submission(client: Client) -> None:
    alpha = label_create("Alpha", Color())
    response = get_list_region(client, {"labels": [alpha.pk]})

    assert hidden_values(parse_html(response.content.decode()), "labels") == [str(alpha.pk)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__omits_label_state_without_label_filter(client: Client) -> None:
    label_create("Alpha", Color())
    response = get_list_region(client)

    assert hidden_values(parse_html(response.content.decode()), "labels") == []


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__empty_state__shown_when_no_match(client: Client) -> None:
    response = get_list_region(client, {"search_term": "definitely-no-such-title-xyz"})

    html = response.content.decode()
    assert "No funding requests match the selected filters." in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sort_by__reorders_entities(client: Client) -> None:
    alpha = modelfactory.fundingrequest(title="AA-alpha request")
    zulu = modelfactory.fundingrequest(title="ZZ-zulu request")
    FundingRequestModel.objects.filter(pk=alpha.pk).update(request_date=date(2024, 1, 1))
    FundingRequestModel.objects.filter(pk=zulu.pk).update(request_date=date(2024, 6, 1))

    default = goto_list_page(client)
    titles = [item.publication_title for item in default.context["entities"]]
    assert titles == ["ZZ-zulu request", "AA-alpha request"]

    alphabetical = goto_list_page(client, {"sort_by": "alphabetical"})
    titles = [item.publication_title for item in alphabetical.context["entities"]]
    assert titles == ["AA-alpha request", "ZZ-zulu request"]

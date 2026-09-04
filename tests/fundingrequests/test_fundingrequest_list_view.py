import re
from collections.abc import Iterator
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import Element, parse_html
from django.urls import reverse

from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.fundingrequest.review import ReviewResult
from tests import modelfactory


def get_list(
    client: Client,
    query: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))


def get_list_region(
    client: Client,
    query: dict[str, Any] | None = None,
) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list_region"), data=query))


def _walk(element: Element) -> Iterator[Element]:
    yield element
    for child in element.children:
        if isinstance(child, Element):
            yield from _walk(child)


def selected_values(dom: Element, name: str) -> list[str]:
    """Return the `selected` option values of the search-select-multi named `name`."""
    for element in _walk(dom):
        attrs = dict(element.attributes)
        if element.name == "search-select-multi" and attrs.get("name") == name:
            return [
                str(dict(option.attributes).get("value", ""))
                for option in _walk(element)
                if option.name == "option" and "selected" in dict(option.attributes)
            ]
    raise AssertionError(f"no <search-select-multi name={name!r}> in page")


def pill_elements(dom: Element) -> list[Element]:
    return [
        element
        for element in _walk(dom)
        if element.name == "a"
        and "label-filter-pill" in (dict(element.attributes).get("class") or "")
    ]


def pill_by_name(dom: Element, name: str) -> Element:
    for element in _walk(dom):
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

    response = get_list(client)
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
    response = get_list(client)

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__counts_each_selected_value(client: Client) -> None:
    label = label_create("Counted Label", Color())

    response = get_list(
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
    response = get_list(client, {"publication_type": "all"})

    assert response.context["filter_count"] == 0


def checked_radio_values(dom: Element, name: str) -> list[str]:
    values: list[str] = []
    for element in _walk(dom):
        attrs = dict(element.attributes)
        if element.name == "input" and attrs.get("name") == name and "checked" in attrs:
            values.append(str(attrs.get("value", "")))
    return values


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_processing_statuses(client: Client) -> None:
    response = get_list(client, {"processing_status": ["approved", "rejected"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "processing_status") == ["approved", "rejected"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_payment_methods(client: Client) -> None:
    response = get_list(client, {"payment_methods": ["direct"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "payment_methods") == ["direct"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__reflects_selected_publication_type(client: Client) -> None:
    response = get_list(client, {"publication_type": "monograph"})

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["monograph"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_ui__defaults_publication_type_to_all(client: Client) -> None:
    response = get_list(client)

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["all"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__returns_fragment_without_page_chrome(client: Client) -> None:
    response = get_list_region(client)

    html = response.content.decode()

    assert "filter-sidebar-form" not in html
    assert "filter-toolbar-form" not in html
    assert "<html" not in html.lower()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__filter_count__excludes_search_and_sort(client: Client) -> None:
    response = get_list(client, {"search_term": "x", "sort_by": "alphabetical"})

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clear_all__shown_with_active_filters(client: Client) -> None:
    label = label_create("Counted Label", Color())
    response = get_list_region(client, {"labels": [label.pk]})

    assert "Clear all" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clear_all__hidden_without_filters(client: Client) -> None:
    response = get_list_region(client)

    assert "Clear all" not in response.content.decode()


def _hidden_label_inputs(html: str) -> list[str]:
    return re.findall(r'<input type="hidden" name="labels" value="(\d+)">', html)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_page__carries_label_state_for_form_submission(client: Client) -> None:
    alpha = label_create("Alpha", Color())
    beta = label_create("Beta", Color())

    response = get_list(client, {"labels": [beta.pk, alpha.pk]})

    assert _hidden_label_inputs(response.content.decode()) == [str(alpha.pk), str(beta.pk)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__carries_label_state_for_form_submission(client: Client) -> None:
    alpha = label_create("Alpha", Color())
    response = get_list_region(client, {"labels": [alpha.pk]})

    assert _hidden_label_inputs(response.content.decode()) == [str(alpha.pk)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region__omits_label_state_without_label_filter(client: Client) -> None:
    label_create("Alpha", Color())
    response = get_list_region(client)

    assert _hidden_label_inputs(response.content.decode()) == []


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__empty_state__shown_when_no_match(client: Client) -> None:
    response = get_list_region(client, {"search_term": "definitely-no-such-title-xyz"})

    html = response.content.decode()

    assert "No funding requests match the selected filters." in html

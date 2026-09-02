from collections.abc import Iterator
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import Element, parse_html
from django.urls import reverse

from coda.contexts.fundingrequest.services.labels import label_create
from coda.domain.color import Color
from coda.domain.fundingrequest.review import ReviewResult


def get_list(
    client: Client,
    query: dict[str, Any] | None = None,
    *,
    hx_request: bool = False,
) -> TemplateResponse:
    kwargs: dict[str, Any] = {}
    if hx_request:
        kwargs["HTTP_HX_Request"] = "true"
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query, **kwargs))


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


def test__selected_values__returns_selected_options() -> None:
    html = (
        '<search-select-multi name="payment_status">'
        '<option slot="options" value="paid" selected>Paid</option>'
        '<option slot="options" value="unpaid">Unpaid</option>'
        "</search-select-multi>"
    )

    assert selected_values(parse_html(html), "payment_status") == ["paid"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__filter_count_is_zero_without_filters(client: Client) -> None:
    response = get_list(client)

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__filter_count_counts_each_selected_value(client: Client) -> None:
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
def test__list_view__filter_count_ignores_default_publication_type(client: Client) -> None:
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
def test__sidebar__marks_selected_processing_statuses(client: Client) -> None:
    response = get_list(client, {"processing_status": ["approved", "rejected"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "processing_status") == ["approved", "rejected"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__marks_selected_payment_methods(client: Client) -> None:
    response = get_list(client, {"payment_methods": ["direct"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "payment_methods") == ["direct"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__marks_selected_publication_type(client: Client) -> None:
    response = get_list(client, {"publication_type": "monograph"})

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["monograph"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__defaults_publication_type_to_all(client: Client) -> None:
    response = get_list(client)

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["all"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__returns_only_list_region_for_htmx_requests(client: Client) -> None:
    response = get_list(client, hx_request=True)

    html = response.content.decode()

    assert "filter-sidebar-form" not in html
    assert "filter-toolbar-form" not in html
    assert "<html" not in html.lower()


def attributes_of(dom: Element, id_value: str) -> dict[str, str | None]:
    for element in _walk(dom):
        attrs = dict(element.attributes)
        if attrs.get("id") == id_value:
            return attrs
    raise AssertionError(f"no element with id={id_value!r} in page")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_page__list_region_has_htmx_attributes(client: Client) -> None:
    response = get_list(client)

    region = attributes_of(parse_html(response.content.decode()), "fundingrequest-list")

    hx_get = str(region.get("hx-get") or "")
    hx_trigger = str(region.get("hx-trigger") or "")
    hx_include = str(region.get("hx-include") or "")

    assert hx_get.endswith("/fundingrequests/list/")
    assert "change from:#filter-sidebar-form" in hx_trigger
    assert "keyup delay:300ms from:#filter-toolbar-form" in hx_trigger
    assert "submit from:#filter-toolbar-form" in hx_trigger
    assert "submit from:#filter-sidebar-form" in hx_trigger
    assert "#filter-sidebar-form" in hx_include
    assert "#filter-toolbar-form" in hx_include
    assert "hx-swap-oob" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_page__old_flat_filter_form_is_gone(client: Client) -> None:
    response = get_list(client)

    dom = parse_html(response.content.decode())
    form_ids = [str(dict(e.attributes).get("id") or "") for e in _walk(dom) if e.name == "form"]

    assert "search-form" not in form_ids
    assert "filter-sidebar-form" in form_ids
    assert "filter-toolbar-form" in form_ids


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__filter_count_excludes_search_and_sort(client: Client) -> None:
    response = get_list(client, {"search_term": "x", "sort_by": "alphabetical"})

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region_partial__includes_out_of_band_header(client: Client) -> None:
    label = label_create("OOB Label", Color())
    response = get_list(client, {"labels": [label.pk]}, hx_request=True)

    html = response.content.decode()

    assert 'hx-swap-oob="true"' in html
    assert 'id="filter-sidebar-header"' in html
    assert "filter-count" in html
    assert "Clear all" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_region_partial__renders_empty_state_on_no_match(client: Client) -> None:
    response = get_list(client, {"search_term": "definitely-no-such-title-xyz"}, hx_request=True)

    html = response.content.decode()

    assert "No funding requests match the selected filters." in html

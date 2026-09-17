"""Business-level readers for the rendered filter sidebar of list pages.

Helpers parse Django's ``parse_html`` trees and key on form field names and
user-visible text (not element ids) so tests stay close to what a user
observes and insensitive to incidental markup changes.
"""

from collections.abc import Iterator

from django.test.html import Element, parse_html


def walk(element: Element) -> Iterator[Element]:
    yield element
    for child in element.children:
        if isinstance(child, Element):
            yield from walk(child)


def _attrs(element: Element) -> dict[str, str | None]:
    return dict(element.attributes)


def _has_class(element: Element, class_name: str) -> bool:
    return class_name in (_attrs(element).get("class") or "").split()


def selected_values(dom: Element, name: str) -> list[str]:
    """Selected option values of the ``search-select-multi`` named ``name``."""
    for element in walk(dom):
        if element.name == "search-select-multi" and _attrs(element).get("name") == name:
            return [
                str(_attrs(option).get("value", ""))
                for option in walk(element)
                if option.name == "option" and "selected" in _attrs(option)
            ]
    raise AssertionError(f"no <search-select-multi name={name!r}> in page")


def selected_option_values(dom: Element, name: str) -> list[str]:
    """Selected option values of the ``<select name=...>`` control named ``name``."""
    for element in walk(dom):
        if element.name == "select" and _attrs(element).get("name") == name:
            return [
                str(_attrs(option).get("value", ""))
                for option in walk(element)
                if option.name == "option" and "selected" in _attrs(option)
            ]
    raise AssertionError(f"no <select name={name!r}> in page")


def checked_radio_values(dom: Element, name: str) -> list[str]:
    """Values of the checked radios named ``name``, in DOM order."""
    return [
        str(_attrs(element).get("value", ""))
        for element in walk(dom)
        if element.name == "input"
        and _attrs(element).get("type") == "radio"
        and _attrs(element).get("name") == name
        and "checked" in _attrs(element)
    ]


def is_checked(dom: Element, name: str) -> bool:
    """Whether the checkbox/switch input named ``name`` renders as checked."""
    for element in walk(dom):
        if (
            element.name == "input"
            and _attrs(element).get("type") == "checkbox"
            and _attrs(element).get("name") == name
        ):
            return "checked" in _attrs(element)
    raise AssertionError(f"no checkbox name={name!r} in page")


def hidden_values(dom: Element, name: str) -> list[str]:
    """Values of the hidden inputs named ``name``, in DOM order."""
    return [
        str(_attrs(element).get("value", ""))
        for element in walk(dom)
        if element.name == "input"
        and _attrs(element).get("type") == "hidden"
        and _attrs(element).get("name") == name
    ]


def clear_all_text(html: str) -> str | None:
    """Text of the clear-all control, None when it isn't rendered."""
    for element in walk(parse_html(html)):
        if element.name == "a" and _has_class(element, "filter-clear"):
            return "".join(c for c in element.children if isinstance(c, str)).strip()
    return None


def chip_texts(dom: Element) -> list[str]:
    """Texts of the active-filter chips, in render order (the × affordance dropped)."""
    texts: list[str] = []
    for element in walk(dom):
        if element.name != "span" or not _has_class(element, "active-filter"):
            continue
        inner = next((c for c in element.children if isinstance(c, Element)), None)
        children = inner.children if inner is not None else []
        texts.append("".join(c for c in children if isinstance(c, str)).strip())
    return texts


def rendered_field_names(dom: Element) -> set[str]:
    """Names of the form controls contained in the rendered markup."""
    field_tags = {"input", "select", "textarea", "search-select", "search-select-multi"}
    return {
        str(_attrs(element).get("name"))
        for element in walk(dom)
        if element.name in field_tags and _attrs(element).get("name")
    }

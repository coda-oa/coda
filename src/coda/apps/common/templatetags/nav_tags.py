from dataclasses import dataclass
from typing import Any

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def nav_is_active(path: str, section: str, match: str = "prefix") -> bool:
    """Whether a nav link is active: exact match, or path within the section (a URL prefix)."""
    if match == "exact":
        return path == section
    return bool(section) and path.startswith(section)


@dataclass(frozen=True)
class NavItem:
    link: str
    text: str
    # If True, also active for group paths no other item matches, so the section
    # always shows one active sub-item (detail pages, wizards, ...).
    default: bool = False


@dataclass(frozen=True)
class NavGroup:
    link: str
    image: str
    text: str
    items: tuple[NavItem, ...]


# Section groups rendered as a top-level entry with a submenu.
NAV_GROUPS: dict[str, NavGroup] = {
    "request_center": NavGroup(
        link="fundingrequests:home",
        image="assets/fundingrequest.svg",
        text="Request Center",
        items=(
            NavItem(link="fundingrequests:list", text="Funding Requests", default=True),
            NavItem(link="fundingrequests:funders", text="Funders"),
        ),
    ),
    "publishing": NavGroup(
        link="publishing:home",
        image="assets/journal.svg",
        text="Journals & Publishers",
        items=(
            NavItem(link="publishing:journals:list", text="Journals"),
            NavItem(link="publishing:publishers:list", text="Publishers"),
            NavItem(link="blocklist:list", text="Blocklist"),
        ),
    ),
    "finances": NavGroup(
        link="invoices:finances_home",
        image="assets/cash.svg",
        text="Finances",
        items=(
            NavItem(link="invoices:list", text="Invoices", default=True),
            NavItem(link="invoices:creditor_list", text="Creditors"),
            NavItem(link="invoices:fundingsource_list", text="Funding Sources"),
        ),
    ),
    "exports": NavGroup(
        link="exports:export_home",
        image="assets/export.svg",
        text="Export",
        items=(
            NavItem(link="exports:fundingrequests_csv_list", text="Funding Requests CSV"),
            NavItem(link="opencost:list", text="openCost Reports"),
        ),
    ),
}


def _group_state(path: str, group: NavGroup) -> dict[str, Any]:
    """Compute which of a group's links are active for ``path``.

    A sub-item is active while ``path`` is within its own URL prefix; the group's
    ``default`` item additionally catches every other path of the group's mount
    (detail pages, wizards, ...), except the hub page itself and any path a
    non-default item already matched. ``group_active`` covers the group's mount and
    every item prefix. Returns the context consumed by ``nav_group.html``.
    """
    group_url = reverse(group.link)
    prefix_matches = {item: path.startswith(reverse(item.link)) for item in group.items}
    group_active = path.startswith(group_url) or any(prefix_matches.values())
    caught_by_other = any(matched and not item.default for item, matched in prefix_matches.items())
    return {
        "link": group.link,
        "image": group.image,
        "text": group.text,
        "path": path,
        "group_active": group_active,
        "items": [
            {
                "link": item.link,
                "text": item.text,
                "active": prefix_matches[item]
                or (item.default and group_active and path != group_url and not caught_by_other),
            }
            for item in group.items
        ],
    }


@register.inclusion_tag("partials/nav_group.html", takes_context=True)
def nav_group(context: dict[str, Any], key: str) -> dict[str, Any]:
    """Render a section group with its submenu; ``key`` selects the group in ``NAV_GROUPS``."""
    request = context["request"]
    return _group_state(request.path, NAV_GROUPS[key])

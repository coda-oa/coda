import html
import re
from typing import Protocol

from django.test import Client
import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from tests import modelfactory
from tests.apps._doubles import InMemoryVersionInfoProvider


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav_template__loads_banner_via_htmx(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    """The nav embeds the HTMX include that fetches the update banner."""
    provider = InMemoryVersionInfoProvider()
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("home"))

    assert 'hx-get="' in response.content.decode()
    assert "check-update" in response.content.decode()


@pytest.mark.django_db
def test__check_update_view__returns_empty_when_no_update(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    """The check-update endpoint renders nothing when no update is available."""
    provider = InMemoryVersionInfoProvider()
    provider.update_info = {"update_available": False}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("check_update"))

    assert "update-banner" not in response.content.decode()


@pytest.mark.django_db
def test__check_update_view__returns_banner_when_update_available(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    """The check-update endpoint renders a banner when a newer commit exists."""
    provider = InMemoryVersionInfoProvider()
    provider.branch = "develop"
    provider.update_info = {"update_available": True, "latest_commit": "abc123"}
    monkeypatch.setattr("coda.apps.version._provider", provider)

    response = client.get(reverse("check_update"))

    assert "update-banner" in response.content.decode()
    assert "develop" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav_template__displays_version(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
) -> None:
    """The nav shows the release version reported by the version provider."""
    provider = InMemoryVersionInfoProvider()
    provider.version = "2026.01"
    monkeypatch.setattr("coda.apps.version._provider", provider)
    response = client.get(reverse("home"))

    assert "Version: 2026.01" in response.content.decode()


class _ResponseLike(Protocol):
    content: bytes


def _nav_html(response: _ResponseLike) -> str:
    """Extract the rendered <aside class="nav-container"> block from a response."""
    html = response.content.decode()
    match = re.search(r'<aside class="nav-container">.*?</aside>', html, re.DOTALL)
    assert match is not None
    return match.group(0)


def _active_nav_items(nav: str) -> set[str]:
    """Return the labels of all nav links carrying the active class."""
    return {
        html.unescape(text).strip()
        for classes, text in re.findall(
            r'<a href="[^"]*"[^>]*class="([^"]*)"[^>]*>.*?<span>([^<]*)</span>',
            nav,
            re.DOTALL,
        )
        if "active" in classes.split()
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__request_center_hub__highlights_parent_only(client: Client) -> None:
    """On a group hub page only the parent entry is active, and exactly one group is active."""
    nav = _nav_html(client.get(reverse("fundingrequests:home")))

    assert 'class="nav__group nav__group--active"' in nav
    assert _active_nav_items(nav) == {"Request Center"}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__funding_request_list__highlights_funding_requests(client: Client) -> None:
    """A path under a sub-item's URL prefix activates that sub-item."""
    nav = _nav_html(client.get(reverse("fundingrequests:list")))

    assert "nav__group--active" in nav
    assert _active_nav_items(nav) == {"Funding Requests"}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__funding_request_detail__highlights_funding_requests(client: Client) -> None:
    """Pages in the group mount outside every sub-item URL fall back to the default item."""
    funding_request = modelfactory.fundingrequest(title="Nav highlight test request")

    nav = _nav_html(client.get(reverse("fundingrequests:detail", args=[funding_request.pk])))

    assert "nav__group--active" in nav
    assert _active_nav_items(nav) == {"Funding Requests"}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__inside_group_mount__exactly_one_group_active(client: Client) -> None:
    """A page inside a group's mount activates the group, and no other group."""
    funding_request = modelfactory.fundingrequest(title="Nav group mount test request")

    nav = _nav_html(client.get(reverse("fundingrequests:detail", args=[funding_request.pk])))

    assert nav.count("nav__group nav__group--active") == 1
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__journal_detail__highlights_journals(client: Client) -> None:
    """A detail page under a sub-item's prefix activates it in a group without a default."""
    journal = modelfactory.journal(title="Nav highlight journal")

    nav = _nav_html(client.get(reverse("publishing:journals:detail", args=[journal.eissn])))

    assert nav.count("nav__group nav__group--active") == 1
    assert _active_nav_items(nav) == {"Journals"}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__blocklist__highlights_blocklist(client: Client) -> None:
    """An item mounted outside its group's mount activates the group via its own prefix."""
    nav = _nav_html(client.get(reverse("blocklist:list")))

    assert nav.count("nav__group nav__group--active") == 1
    assert _active_nav_items(nav) == {"Blocklist"}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__contract_detail__highlights_contracts(client: Client) -> None:
    """A flat item is active across its whole URL prefix, and deep pages activate no group."""
    contract = modelfactory.contract()

    nav = _nav_html(client.get(reverse("contracts:detail", args=[contract.pk])))

    assert "nav__group--active" not in nav
    assert _active_nav_items(nav) == {"Contracts"}


def test__nav_link__section_prefix__active_outside_item_url() -> None:
    """A flat item's section prefix keeps it active on pages outside its own item URL."""
    html = render_to_string(
        "partials/nav_link.html",
        {
            "path": "/publications/vocabulary/edit/save",
            "link": "publications:vocabularies",
            "text": "Vocabularies",
            "section": "/publications/",
        },
    )

    assert 'class="contrast active"' in html
    assert 'aria-current="page"' in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__nav__home__no_item_active(client: Client) -> None:
    """The home page leaves every nav item inactive."""
    nav = _nav_html(client.get(reverse("home")))

    assert "nav__group--active" not in nav
    assert _active_nav_items(nav) == set()

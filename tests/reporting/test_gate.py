"""The ``CODA_STATISTICS_ENABLED`` gate locks every statistics surface shut.

Test settings enable the gate (config/settings/test.py); these tests turn it
off to pin the closed state. The gated entry points, each covered below:

- the statistics page, its HTMX region and the CSV export answer 404 — the
  page requested with an explicit period, so a gate that fails open cannot
  hide behind the default-period redirect;
- the funding-request list renders neither the Statistics button nor the
  nav entry;
- the reporting home page renders no statistics card.

Any future statistics surface needs a disabled-state test here."""

from http import HTTPStatus

import pytest
from django.test import Client, override_settings
from django.test.html import Element, parse_html
from django.urls import reverse

from tests.filterdom import walk

_PERIOD = {"start_date": "2026-01-01", "end_date": "2026-12-31"}

_STATISTICS_URLS = [
    ("reporting:stats_fundingrequests", {}),
    ("reporting:stats_fundingrequests_region", {}),
    ("reporting:stats_fundingrequests_export", {"dimension_id": "publisher"}),
]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize(("url_name", "url_kwargs"), _STATISTICS_URLS)
def test__gate_disabled__statistics_urls_answer_404(
    client: Client, url_name: str, url_kwargs: dict[str, str]
) -> None:
    with override_settings(CODA_STATISTICS_ENABLED=False):
        response = client.get(reverse(url_name, kwargs=url_kwargs), data=_PERIOD)

    assert response.status_code == HTTPStatus.NOT_FOUND


def _has_statistics_link(dom: Element) -> bool:
    return any(
        element.name == "a" and dict(element.attributes).get("id") == "statistics-link"
        for element in walk(dom)
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__gate_disabled__list_hides_statistics_button_and_nav_entry(client: Client) -> None:
    with override_settings(CODA_STATISTICS_ENABLED=False):
        response = client.get(reverse("fundingrequests:list"))

    html = response.content.decode()
    assert not _has_statistics_link(parse_html(html))
    assert "Funding Request Statistics" not in html


# Card-specific copy: "Funding Request Statistics" also appears in the nav
# submenu, so only this string pins the reporting home card itself.
_CARD_COPY = "Publications funded and spend per dimension"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__gate_disabled__reporting_home_hides_statistics_card(client: Client) -> None:
    with override_settings(CODA_STATISTICS_ENABLED=False):
        response = client.get(reverse("reporting:home"))

    assert _CARD_COPY not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__gate_enabled__reporting_home_shows_statistics_card(client: Client) -> None:
    response = client.get(reverse("reporting:home"))

    assert _CARD_COPY in response.content.decode()

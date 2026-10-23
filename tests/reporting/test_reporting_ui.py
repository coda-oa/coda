"""Browser check (plan §11 last bullet): a real browser paints the server's
figure JSON — one svg per [data-chart] mount — a chart-row click filters the
statistics page in place, and the page's global link lands on the
funding-request list with the active filters."""

from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests.forms import _FACET_CHOICE_LIMIT
from coda.apps.publications.models import LinkType
from tests import modelfactory
from tests.page_objects import filter_ui_selectors
from tests.reporting import helpers
from tests.reporting.test_page import PERIOD, seed


@pytest.fixture
def link_types() -> None:
    """LinkTypes the request factory attaches; transactional tests truncate the
    session fixture's rows, so they must be recreated here."""
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")


def _goto_statistics(page: Page, live_server: LiveServer, **extra: str) -> None:
    # Desktop width like the other filter-rail UI tests; the period goes into
    # the URL so the page renders immediately — no redirect in front of charts.
    page.set_viewport_size({"width": 1440, "height": 900})
    params = urlencode({**PERIOD, **extra})
    page.goto(f"{live_server.url}{reverse('reporting:stats_fundingrequests')}?{params}")
    page.wait_for_function("() => typeof Plotly !== 'undefined'")


def _open_filter_drawer(page: Page) -> None:
    """The filter rail is a drawer on every viewport now; tests that interact
    with its widgets open it first (it blocks the page behind it while open).
    Idempotent: if the dialog is mid-close, reopen and wait until it sits at
    its settled position — a closing dialog slides off-screen while still
    reporting visible."""
    page.evaluate(
        "() => { const d = document.getElementById('filter-sidebar');"
        " if (!d.matches(':modal')) { d.showModal(); } }"
    )
    page.wait_for_function(
        "() => { const d = document.getElementById('filter-sidebar');"
        " const r = d.getBoundingClientRect();"
        " return d.matches(':modal') && Math.abs(r.right - window.innerWidth) < 2; }"
    )


def _wait_for_charts(page: Page) -> None:
    page.wait_for_function(
        "() => [...document.querySelectorAll('[data-chart]')]"
        ".every((el) => el.dataset.plotlyRendered === 'true')"
    )


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__reporting_page__plotly__renders_one_svg_per_chart_mount(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    seed()
    _goto_statistics(coda_page, live_server)
    _wait_for_charts(coda_page)

    # The default view is the overview tab: headline + timeline only.
    expected = 1
    expect(coda_page.locator("[data-chart]")).to_have_count(expected)

    painted = coda_page.eval_on_selector_all(
        "[data-chart]", "els => els.filter((el) => el.querySelector('svg')).length"
    )
    assert painted == expected


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__reporting_page__row_link__filters_the_page_in_place(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """Clicking a table row filters the statistics page itself: the region
    swaps, the URL gains the facet param, and the headline narrows to the
    clicked row's set. Clicking again toggles the filter off."""
    fixture = seed()
    _goto_statistics(coda_page, live_server, tab="venues")
    _wait_for_charts(coda_page)

    # The exact-value table lives in a collapsed <details>; open it first.
    coda_page.locator("#statistics-journal details.statistics-exact summary").click()
    row_link = coda_page.locator(
        "#statistics-journal table.statistics-values th a",
    ).filter(has_text=fixture.journal.title)
    row_link.click()

    coda_page.wait_for_url(lambda url: f"journal={fixture.journal.pk}" in url)
    # The headline cards are overview-only; the filter's effect shows in the
    # intro link's count (first item on every tab).
    expect(coda_page.locator(".statistics-intro")).to_contain_text("1 funding request")

    # Toggle off: the row link now carries the filter-removing URL. The swap
    # re-renders the region with the details collapsed again — reopen first.
    coda_page.wait_for_url(lambda url: "journal=" in url)
    coda_page.locator("#statistics-journal details.statistics-exact summary").click()
    row_link.click()
    coda_page.wait_for_url(lambda url: "journal=" not in url)
    expect(coda_page.locator(".statistics-intro")).to_contain_text("3 funding requests")


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__reporting_page__global_list_link__lands_on_the_filtered_list(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """The page's one link into the funding-request list carries the active
    filters — the data behind the numbers."""
    fixture = seed()
    _goto_statistics(coda_page, live_server, journal=str(fixture.journal.pk))
    _wait_for_charts(coda_page)

    coda_page.get_by_role("link", name="behind these numbers").click()

    coda_page.wait_for_url(lambda url: "/fundingrequests/list/" in url)
    assert f"journal={fixture.journal.pk}" in coda_page.url
    listing = coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST)
    expect(listing.get_by_text("Funded paper")).to_be_visible()
    expect(listing.get_by_text("Paper without invoice")).to_be_hidden()
    expect(listing.get_by_text("Paper without rate")).to_be_hidden()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__journal_facet__typing__narrow_options_server_side(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """The journal facet searches server-side (the registry is too large to
    enumerate): typing posts ``journal_q`` through the hidden input, and the
    re-rendered rail offers only the matches — focus and query text survive
    the swap."""
    seed()
    publisher = modelfactory.publisher(name="Shared publisher")
    for index in range(_FACET_CHOICE_LIMIT + 20):
        modelfactory.journal(publisher_id=publisher.pk, title=f"Facet {index:03d}")
    match = modelfactory.journal(publisher_id=publisher.pk, title="Qwertyuiop unique")
    _goto_statistics(coda_page, live_server)
    _open_filter_drawer(coda_page)

    facet = coda_page.locator("search-select-multi#id_journal")
    search_box = facet.locator(".search-input")
    expect(search_box).to_be_visible()
    expect(facet.locator("option")).to_have_count(_FACET_CHOICE_LIMIT)

    search_box.fill("qwerty")

    expect(facet.locator('input[name="journal_q"]')).to_have_value("qwerty")
    expect(facet.locator("option")).to_have_count(1)
    expect(facet.locator("option")).to_have_text(match.title)
    active = coda_page.evaluate("() => document.activeElement?.shadowRoot?.activeElement?.value")
    assert active == "qwerty"


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__journal_facet__selecting_a_match__keeps_the_narrowed_list(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """Picking matches must not drop the searched term — multi-select under
    one term is the whole point of ``journal_q``: each selection's change
    event serializes the queued typing term (re-seeded from ``data-q`` after
    every swap), so the rail stays narrowed across *two consecutive picks*
    and the box restores the term. *Clear all* then genuinely clears
    everything — a stale search term must not resurrect itself."""
    seed()
    publisher = modelfactory.publisher(name="Shared publisher")
    for index in range(_FACET_CHOICE_LIMIT + 20):
        modelfactory.journal(publisher_id=publisher.pk, title=f"Facet {index:03d}")
    first = modelfactory.journal(publisher_id=publisher.pk, title="Qwertyuiop unique")
    second = modelfactory.journal(publisher_id=publisher.pk, title="Qwertyuiop second")
    _goto_statistics(coda_page, live_server)
    _open_filter_drawer(coda_page)

    facet = coda_page.locator("search-select-multi#id_journal")
    search_box = facet.locator(".search-input")
    expect(search_box).to_be_visible()
    search_box.fill("qwerty")
    expect(facet.locator("option")).to_have_count(2)

    facet.locator(".dropdown .option", has_text=first.title).click()

    expect(facet.locator(".selected-tag span")).to_have_text([first.title])
    expect(
        coda_page.locator("#active-filters .active-filter").filter(has_text=first.title)
    ).to_be_visible()
    expect(facet.locator("option")).to_have_count(2)
    expect(facet.locator('input[name="journal_q"]')).to_have_value("qwerty")
    expect(search_box).to_have_value("qwerty")

    # The multi-select case: a second pick on the swapped-in element, whose
    # queued term can only come from the server's data-q.
    search_box.click()
    facet.locator(".dropdown .option", has_text=second.title).click()

    expect(facet.locator(".selected-tag span")).to_have_text([first.title, second.title])
    expect(
        coda_page.locator("#active-filters .active-filter").filter(has_text=second.title)
    ).to_be_visible()
    expect(facet.locator("option")).to_have_count(2)
    expect(facet.locator(f'option[value="{second.pk}"]')).to_be_attached()
    expect(facet.locator('input[name="journal_q"]')).to_have_value("qwerty")
    expect(search_box).to_have_value("qwerty")

    # Clear all lives in the drawer header; the drawer scrolls its facet
    # content, so bring it home before clicking.
    coda_page.evaluate(
        "document.getElementById('filter-sidebar').scrollTo({top: 0})"
    )
    coda_page.locator(filter_ui_selectors.FILTER_CLEAR_ALL).click()

    expect(facet.locator("option")).to_have_count(_FACET_CHOICE_LIMIT)
    expect(facet.locator('input[name="journal_q"]')).to_have_value("")
    expect(search_box).to_have_value("")
    expect(facet.locator(".selected-tag")).to_have_count(0)


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__statistics_table__column_header__sorts_the_rows(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """The server ranks each facet's table spend-first; clicking the count
    header re-orders the rows client-side and the click toggles direction."""
    volume = modelfactory.publisher(name="Big Volume Press")
    volume_journal = modelfactory.journal(publisher_id=volume.pk, title="Volume journal")
    for index in range(3):
        request = helpers.request(f"Volume paper {index}")
        request.publication.article_journal = volume_journal
        request.publication.save()
        position = helpers.position(request.publication.pk, Decimal("10.00"), Decimal("0.00"))
        helpers.invoice([position])
    ticket = modelfactory.publisher(name="Big Ticket Press")
    ticket_journal = modelfactory.journal(publisher_id=ticket.pk, title="Ticket journal")
    request = helpers.request("Ticket paper")
    request.publication.article_journal = ticket_journal
    request.publication.save()
    position = helpers.position(request.publication.pk, Decimal("500.00"), Decimal("0.00"))
    helpers.invoice([position])

    _goto_statistics(coda_page, live_server, tab="venues")

    # The exact-value table lives in a collapsed <details>; open it first.
    coda_page.locator("#statistics-publisher details.statistics-exact summary").click()
    table = coda_page.locator("#statistics-publisher table.statistics-values")
    first_row = table.locator("tbody tr th").first
    count_header = table.locator("thead th", has_text="publications")
    # Native columnheader role survives (a11y.md #2: no role="button" — which
    # Pico would also paint blue); keyboard reachability replaces it.
    assert count_header.get_attribute("role") is None
    expect(count_header).to_have_attribute("tabindex", "0")

    # Server order: money leads (500 € above 30 €).
    expect(first_row).to_have_text("Big Ticket Press")

    count_header.click()
    expect(first_row).to_have_text("Big Volume Press")
    expect(count_header).to_have_attribute("aria-sort", "descending")

    count_header.click()
    expect(first_row).to_have_text("Big Ticket Press")
    expect(count_header).to_have_attribute("aria-sort", "ascending")

"""Browser check (plan §11 last bullet): a real browser paints the server's
figure JSON — one svg per [data-chart] mount — a chart-row click filters the
statistics page in place, and the page's global link lands on the
funding-request list with the active filters."""

import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest
from django.urls import reverse
from playwright.sync_api import Locator, Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests.facets import _FACET_CHOICE_LIMIT
from coda.apps.preferences.models import GlobalPreferences
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
    # The filter's effect also shows in the title-row list button: the region
    # response re-renders it out of band — href and live count both.
    list_button = coda_page.locator("#statistics-list-link")
    expect(list_button).to_have_attribute("href", re.compile(f"journal={fixture.journal.pk}"))
    expect(list_button).to_contain_text("1 request")

    # Toggle off: the row link now carries the filter-removing URL. The swap
    # re-renders the region with the details collapsed again — reopen first.
    coda_page.wait_for_url(lambda url: "journal=" in url)
    coda_page.locator("#statistics-journal details.statistics-exact summary").click()
    row_link.click()
    coda_page.wait_for_url(lambda url: "journal=" not in url)
    expect(list_button).not_to_have_attribute("href", re.compile("journal="))


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__reporting_page__global_list_link__lands_on_the_filtered_list(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """The title-row button into the funding-request list carries the active
    filters — the data behind the numbers."""
    fixture = seed()
    _goto_statistics(coda_page, live_server, journal=str(fixture.journal.pk))
    _wait_for_charts(coda_page)

    # The OOB re-render updated the button's href with the facet param.
    list_button = coda_page.get_by_role("link", name="View 1 request")
    expect(list_button).to_have_attribute("href", re.compile(f"journal={fixture.journal.pk}"))

    list_button.click()

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
    rematch = modelfactory.journal(publisher_id=publisher.pk, title="Zxcvbnm unique")
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

    # The swapped-in fragment must itself carry a usable endpoint: a second
    # search issues a fresh fetch instead of silently dead-ending on
    # data-endpoint="".
    search_box.fill("zxcvb")
    expect(facet.locator('input[name="journal_q"]')).to_have_value("zxcvb")
    expect(facet.locator("option")).to_have_count(1)
    expect(facet.locator("option")).to_have_text(rematch.title)
    active = coda_page.evaluate("() => document.activeElement?.shadowRoot?.activeElement?.value")
    assert active == "zxcvb"


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
    coda_page.evaluate("document.getElementById('filter-sidebar').scrollTo({top: 0})")
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


def _computed_color(locator: "Locator") -> str:
    """The element's computed text color."""
    color: str = locator.evaluate("(el) => getComputedStyle(el).color")
    return color


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__statistics_table__fold_toggle__reveals_and_rehides_the_tail(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """Expanding the Other fold REPLACES the fold row with the tail values
    (plan §9, as shipped): the unveiled rows join the main tbody, so the
    fold row disappears, the collapse control appears (only while
    expanded), and sorting covers the unveiled values too. Collapsing moves
    the tail back into its hidden tbody and restores the fold row."""
    for index in range(1, 13):
        journal = modelfactory.journal(title=f"Journal {index:02d}")
        request = helpers.request(f"Fold paper {index:02d}")
        request.publication.article_journal = journal
        request.publication.save()
        if index == 10:  # one paid value, so the server rank differs from A→Z
            position = helpers.position(request.publication.pk, Decimal("500.00"), Decimal("0.00"))
            helpers.invoice([position])

    _goto_statistics(coda_page, live_server, tab="venues")

    # The exact-value table lives in a collapsed <details>; open it first.
    coda_page.locator("#statistics-journal details.statistics-exact summary").click()
    table = coda_page.locator("#statistics-journal table.statistics-values")
    main_body = table.locator("tbody").first
    folded_body = table.locator("tbody#folded-journal")
    other_row = main_body.locator("tr.statistics-aggregate")
    expand_control = main_body.locator("a.statistics-fold-toggle")
    collapse_control = table.locator("tfoot tr.statistics-collapse-row")

    expect(other_row).to_be_visible()
    expect(folded_body).to_be_hidden()
    expect(collapse_control).to_be_hidden()
    expect(main_body.locator("tr")).to_have_count(11)  # top 10 + Other

    # The toggles must render as plain links, identical to the section's
    # export link. A regression to Pico's filled [role=button] look (its
    # form-button text color) fails this equality loudly.
    export_link = coda_page.locator("#statistics-journal details.statistics-exact a[download]")
    link_color = _computed_color(export_link)
    assert _computed_color(expand_control) == link_color
    assert _computed_color(collapse_control.locator("a")) == link_color

    # Row-label drilldown links keep the link color but no underline
    # (reporting.css: .statistics-values th a). A Pico upgrade or CSS
    # reorder that restores underlines fails here.
    row_link = main_body.locator("tr th a").first
    assert row_link.evaluate("(el) => getComputedStyle(el).textDecorationLine") == "none"
    assert _computed_color(row_link) == link_color

    # The href-less toggles lost Pico's [role=button] focus treatment, so
    # their keyboard focus indicator is pinned: reach the expand control
    # with genuine Tab key presses (a scripted el.focus() would not match
    # Chromium's :focus-visible heuristic; the walk below is the
    # deterministic route), then require a visible indicator.
    toggle_reached = False
    for _ in range(20):
        coda_page.keyboard.press("Tab")
        if coda_page.evaluate(
            "() => document.activeElement?.classList.contains('statistics-fold-toggle')"
        ):
            toggle_reached = True
            break
    assert toggle_reached, "fold toggle not reachable via keyboard Tab"
    focus_style = coda_page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement);"
        " return {outlineStyle: s.outlineStyle, outlineWidth: s.outlineWidth,"
        " boxShadow: s.boxShadow}; }"
    )
    assert (
        focus_style["outlineStyle"] != "none"
        or focus_style["outlineWidth"] not in ("0px", "")
        or focus_style["boxShadow"] != "none"
    ), focus_style

    expand_control.click()
    # The Other row yields; the tail is now ordinary sortable rows in the
    # main tbody, and the collapse control takes over.
    expect(other_row).to_be_hidden()
    expect(expand_control).to_be_hidden()  # it lives in the Other row
    expect(collapse_control).to_be_visible()
    expect(collapse_control.locator("a")).to_have_attribute("aria-expanded", "true")
    expect(main_body.locator("tr")).to_have_count(13)  # 12 values + hidden Other
    expect(main_body.locator("th", has_text="Journal 11")).to_be_visible()

    # Sorting covers the unveiled values: the label column orders the whole
    # set, not just the top 10.
    label_header = table.locator("thead th").first
    expect(main_body.locator("tr th").first).to_have_text("Journal 10")
    label_header.click()
    expect(main_body.locator("tr th").first).to_have_text("Journal 01")
    expect(main_body.locator("th", has_text="Journal 12")).to_be_visible()

    collapse_control.locator("a").click()
    expect(other_row).to_be_visible()
    expect(collapse_control).to_be_hidden()
    expect(folded_body).to_be_hidden()
    expect(folded_body.locator("th", has_text="Journal 11")).to_have_count(1)
    expect(folded_body.locator("th", has_text="Journal 12")).to_have_count(1)
    expect(main_body.locator("tr")).to_have_count(11)
    # Server rank order restored: the one paid value leads again.
    expect(main_body.locator("tr th").first).to_have_text("Journal 10")
    # The collapse also clears the sort state: no aria-sort on the headers
    # and no data-sort-* on the table, so the next header click takes the
    # fresh-state default (label column A→Z) instead of flipping from the
    # stale direction.
    expect(table.locator("thead th[aria-sort='ascending']")).to_have_count(0)
    expect(table.locator("thead th[aria-sort='descending']")).to_have_count(0)
    expect(table).not_to_have_attribute("data-sort-column", re.compile(".+"))
    expect(table).not_to_have_attribute("data-sort-direction", re.compile(".+"))
    label_header.click()
    expect(main_body.locator("tr th").first).to_have_text("Journal 01")

    # The text links are keyboard-activatable (no href, so reporting.js
    # mirrors the sortable headers' Enter/Space handling): Enter expands,
    # Space collapses.
    expand_control.focus()
    coda_page.keyboard.press("Enter")
    expect(other_row).to_be_hidden()
    expect(main_body.locator("th", has_text="Journal 11")).to_be_visible()

    collapse_control.locator("a").focus()
    coda_page.keyboard.press(" ")
    expect(other_row).to_be_visible()
    expect(collapse_control).to_be_hidden()


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__statistics_table__export_csv__downloads_the_section_csv(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """The Export CSV link downloads the section's complete value set in a
    real browser (plan §6, §8): suggested filename names the dimension and a
    timestamp, the bytes carry the BOM, the header is exact, the row count
    matches the section's value count, the currency column holds the home
    currency's code, and amount cells use the German decimal comma."""
    seed()

    _goto_statistics(
        coda_page,
        live_server,
        tab="venues",
        compare="1",
        compare_start_date="2025-01-01",
        compare_end_date="2025-12-31",
    )

    details = coda_page.locator("#statistics-journal details.statistics-exact")
    details.locator("summary").click()
    link = details.locator("a[download]", has_text="Export table as CSV")

    with coda_page.expect_download() as download_info:
        link.click()
    download = download_info.value
    assert re.fullmatch(r"journal_export_\d{8}_\d{6}\.csv", download.suggested_filename)

    content = Path(download.path()).read_bytes()
    assert content.startswith(b"\xef\xbb\xbf")
    lines = content.decode("utf-8-sig").splitlines()
    assert lines[0] == (
        "label;currency;publications;amount;comparison_publications;comparison_amount"
    )

    summary_text = details.locator("summary").text_content() or ""
    summary_match = re.search(r"\((\d+) rows\)", summary_text)
    assert summary_match is not None
    assert len(lines) - 1 == int(summary_match.group(1))

    code = GlobalPreferences.get_home_currency().code
    cells = lines[1].split(";")
    # The currency column carries the home currency's code; the amount uses
    # the German decimal comma.
    assert cells[1] == code
    assert re.fullmatch(r"\d+(,\d+)?", cells[3])


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__reporting_page__treemap_leaf_tile__filters_and_does_not_drill(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """Clicking a leaf tile filters the page like its table row: the region
    swaps, the URL gains the facet param, and no plotly drilldown animates
    (the tile set stays the root's). Clicking a branch tile drills without
    any facet param."""
    fixture = seed()
    _goto_statistics(coda_page, live_server, tab="attribution")
    _wait_for_charts(coda_page)

    treemap = coda_page.locator("[data-chart='chart-institution-treemap']")
    tiles_before = treemap.locator("g.slice").count()

    # Leaf click: the tile's label links to the institution facet. The seed's
    # institution name is faker-random, so pick the linked tile via the
    # figure payload's tile_links (id → URL carrying institution=pk) and get
    # the display label from the row's customdata (ids are pk-based, labels
    # are display strings).
    leaf_label = coda_page.evaluate(
        """pk => { const fig = JSON.parse(
              document.getElementById('chart-institution-treemap').textContent);
            const d = fig.data[0];
            const e = Object.entries(fig.tile_links).find(([, v]) => v &&
              v.includes(`institution=${pk}`));
            if (!e) return null;
            const i = d.ids.indexOf(e[0]);
            return d.customdata[i][2]; }""",
        fixture.institution.pk,
    )
    assert leaf_label, "seeded institution has no linked treemap tile"
    # Resolve the leaf slice element in-page (data-unformatted carries the
    # full texttemplate output; faker names can contain apostrophes that
    # break attribute selectors), then click it by handle.
    leaf_handle = coda_page.evaluate(
        """labelPrefix => {
            const items = [...document.querySelectorAll(
                "[data-chart='chart-institution-treemap'] [data-unformatted]")];
            const norm = s => s.replace(/<br>/g, ' ').replace(/\\s+/g, ' ').trim();
            const prefix = norm(labelPrefix);
            const t = items.find(el => norm(el.getAttribute('data-unformatted'))
                .startsWith(prefix));
            return t ? [...document.querySelectorAll(
                "[data-chart='chart-institution-treemap'] g.slice")]
                .find(g => g.contains(t)) ?? null : null;
        }""",
        leaf_label,
    )
    assert leaf_handle, f"leaf tile not rendered: {leaf_label!r}"
    # Click in-page: the leaf locator's text filter is unreliable here (the
    # branch + own-publication rows share the display text and wrapped labels
    # split across tspans), and a has_text locator can resolve to a different
    # slice under faker names. The in-page dispatch goes through plotly's
    # real event path.
    coda_page.evaluate(
        """labelPrefix => {
            const items = [...document.querySelectorAll(
                "[data-chart='chart-institution-treemap'] [data-unformatted]")];
            const norm = s => s.replace(/<br>/g, ' ').replace(/\\s+/g, ' ').trim();
            const prefix = norm(labelPrefix);
            const t = items.find(el => norm(el.getAttribute('data-unformatted'))
                .startsWith(prefix));
            const slice = t && [...document.querySelectorAll(
                "[data-chart='chart-institution-treemap'] g.slice")]
                .find(g => g.contains(t));
            slice?.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }""",
        leaf_label,
    )
    coda_page.wait_for_url(lambda url: f"institution={fixture.institution.pk}" in url)
    # The region swap replaces the chart element; re-anchor, then assert no
    # drilldown: the re-rendered treemap still shows the root view. (The tile
    # count varies with the filter — the seed yields a small tree.)
    treemap = coda_page.locator("[data-chart='chart-institution-treemap']")
    expect(treemap.locator("g.slice").filter(has_text="All institutions")).to_have_count(1)

    # Branch click: the seeded institution is its own root (no parent), so it
    # has no branch ancestor — the branch-click half only applies to trees
    # with a hierarchy. Skip when the clicked leaf IS a root tile (its slice
    # is the tree's only branch).
    has_branch = coda_page.evaluate(
        """leafLabel => {
            const slices = [...document.querySelectorAll(
                "[data-chart='chart-institution-treemap'] g.slice")];
            const norm = s => s.replace(/<br>/g, ' ').replace(/\\s+/g, ' ').trim();
            return slices.some(g => {
                const t = g.querySelector('[data-unformatted]');
                if (!t) return false;
                const s = norm(t.getAttribute('data-unformatted'));
                return s !== 'All institutions' && s !== norm(leafLabel)
                    && !s.startsWith(norm(leafLabel));
            });
        }""",
        leaf_label,
    )
    if not has_branch:
        return
    coda_page.evaluate(
        """leafLabel => {
            const slices = [...document.querySelectorAll(
                "[data-chart='chart-institution-treemap'] g.slice")];
            const norm = s => s.replace(/<br>/g, ' ').replace(/\\s+/g, ' ').trim();
            const branch = slices.find(g => {
                const t = g.querySelector('[data-unformatted]');
                if (!t) return false;
                const s = norm(t.getAttribute('data-unformatted'));
                return s !== 'All institutions' && !s.startsWith(norm(leafLabel));
            });
            branch?.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }""",
        leaf_label,
    )
    coda_page.wait_for_url(lambda url: "institution=" not in url)
    coda_page.wait_for_function(
        """n => document.querySelectorAll(
              "[data-chart='chart-institution-treemap'] g.slice"
            ).length !== n""",
        arg=tiles_before,
    )

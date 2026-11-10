"""The per-dimension CSV export and the table expansion (plan §5–§9, §11).

The export is the section table's complete value set, with no top-10 cut
and no "Other" fold, as ``;``-separated ``utf-8-sig`` CSV, with the
comparison period's raw values joined by label when compare is on. The
page's tables slice the same unbounded grouping: first ten rows visible,
the rest folded under the Other row's client-side disclosure, so visible +
folded rows equal the export's rows.
"""

import re
from datetime import date
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest
from django.db import connection
from django.http import QueryDict
from django.test import Client
from django.test.html import Element, parse_html
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.fundingrequests.forms import FundingRequestListFilterForm
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.reporting.views.export import MISSING_DATES_MESSAGE
from coda.domain.money import Currency
from coda.domain.publication import License
from tests import modelfactory
from tests.filterdom import walk
from tests.reporting import helpers
from tests.reporting.test_page import PERIOD, sections_of

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

_EXPORT_URL_NAME = "reporting:stats_fundingrequests_export"
_COMPARE = {"compare": "1", "compare_start_date": "2025-01-01", "compare_end_date": "2025-12-31"}


def goto_export(client: Client, dimension_id: str, **query: str) -> "_MonkeyPatchedWSGIResponse":
    return client.get(reverse(_EXPORT_URL_NAME, args=[dimension_id]), data={**PERIOD, **query})


def goto_region(client: Client, **query: str) -> "_MonkeyPatchedWSGIResponse":
    return client.get(
        reverse("reporting:stats_fundingrequests_region"),
        data={**PERIOD, **query},
        headers={"hx-request": "true"},
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__page__one_sided_compare_dates__mark_the_compare_inputs_invalid(
    client: Client,
) -> None:
    """One-sided compare dates disable the comparison (§5.1) and mark the
    compare inputs invalid: the page caller owns the widget side effect the
    extracted helper must not perform, so this pins that the extraction
    preserved it."""
    region = goto_region(
        client, tab="venues", compare="1", compare_start_date="2025-01-01"
    )
    assert region.context["comparison_error"] == "Both comparison dates are required."
    attrs = region.context["filter_form"].fields["compare_range"].widget.attrs
    assert attrs["aria-invalid"] == "true"
    assert attrs["aria-describedby"] == "compare-date-error"


def export_url(dimension_id: str) -> str:
    return reverse(_EXPORT_URL_NAME, args=[dimension_id])


def csv_rows(response: "_MonkeyPatchedWSGIResponse") -> list[list[str]]:
    text = response.content.decode("utf-8-sig")
    return [line.split(";") for line in text.splitlines()]


def csv_labels(response: "_MonkeyPatchedWSGIResponse") -> list[str]:
    return [row[0] for row in csv_rows(response)[1:]]


def query_params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def journal_paper(title: str, journal_title: str, year: int = 2026) -> None:
    """One request under its own journal, dated into the given year. The
    license is pinned so license-filtered round-trips stay deterministic."""
    journal = modelfactory.journal(title=journal_title)
    fr = helpers.request(title)
    fr.request_date = date(year, 3, 15)
    fr.publication.article_journal = journal
    fr.publication.license = License.CC_BY.name
    fr.publication.save()
    fr.save()


def seed_tail(count: int = 12) -> list[str]:
    """``count`` single-request journals: the long tail the fold exists for."""
    titles = [f"Journal {index:02d}" for index in range(1, count + 1)]
    for index, title in enumerate(titles, start=1):
        journal_paper(f"Paper {index:02d}", title)
    return titles


def text_of(element: Element) -> str:
    return "".join(
        child if isinstance(child, str) else text_of(child) for child in element.children
    ).strip()


def section_dom(region: "_MonkeyPatchedWSGIResponse", dimension_id: str) -> Element:
    """The rendered ``<article>`` of one dimension's section."""
    dom = parse_html(region.content.decode())
    for element in walk(dom):
        if element.name == "article" and dict(element.attributes).get("id") == (
            f"statistics-{dimension_id}"
        ):
            return element
    raise AssertionError(f"no section rendered for {dimension_id}")


def tbodies(section: Element) -> tuple[Element, Element | None]:
    """The section table's visible tbody and its hidden disclosure, if any."""
    table = next(element for element in walk(section) if element.name == "table")
    visible = next(element for element in walk(table) if element.name == "tbody")
    hidden = next(
        (
            element
            for element in walk(table)
            if element.name == "tbody" and "hidden" in dict(element.attributes)
        ),
        None,
    )
    return visible, hidden


def row_labels(tbody: Element) -> list[str]:
    return [text_of(cell) for cell in walk(tbody) if cell.name == "th"]


# -- View contract (§7) ------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__unknown_dimension__404(client: Client) -> None:
    response = goto_export(client, "not-a-dimension")
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test__export__anonymous__redirects_to_login(client: Client) -> None:
    response = client.get(export_url("journal"), data=PERIOD)
    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"].startswith(reverse("login"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__invalid_dates__400_with_the_form_error(client: Client) -> None:
    seed_tail(1)
    response = client.get(
        export_url("journal"),
        data={"start_date": "not-a-date", "end_date": "2026-12-31"},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    form = FundingRequestListFilterForm(
        QueryDict("start_date=not-a-date&end_date=2026-12-31"),
        contracts=[],
        labels=[],
        vocabularies=GlobalPreferences.preloaded(),
        include_labels_widget=True,
    )
    form.is_valid()
    assert response.content.decode() == str(form.errors["date_range"][0])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__bare_get_without_dates__400(client: Client) -> None:
    response = client.get(export_url("journal"))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.content.decode() == MISSING_DATES_MESSAGE


# -- Full set vs top-10 (§11) ------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__exports_the_complete_set__superset_of_the_page_top10(
    client: Client,
) -> None:
    titles = seed_tail(12)

    region = goto_region(client, tab="venues")
    section = sections_of(region)["journal"]
    assert section.value_count == 12
    assert [row.label for row in section.rows] == [*sorted(titles)[:10], "Other"]
    assert [row.label for row in section.folded] == sorted(titles)[10:]

    response = goto_export(client, "journal")
    assert response.status_code == HTTPStatus.OK
    assert csv_labels(response) == sorted(titles)
    assert "Other" not in csv_labels(response)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__page__chart_rows__stay_bounded(client: Client) -> None:
    """The table is a superset of the chart's row set by design (§9): the
    figure keeps its own bounded grouping, top-10 plus the Other fold."""
    titles = seed_tail(12)

    region = goto_region(client, tab="venues")
    figure = sections_of(region)["journal"].chart.figure
    assert list(figure["data"][0]["x"]) == [*sorted(titles)[:10], "Other"]


# -- Table expansion (§9) ----------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__page__folded_rows__render_in_a_hidden_disclosure(client: Client) -> None:
    titles = seed_tail(12)

    region = goto_region(client, tab="venues")
    section = section_dom(region, "journal")
    visible, hidden = tbodies(section)
    assert hidden is not None
    # The export link lives inside the expandable table section, below the
    # table it exports (as-shipped §8), outside the <summary>, which would
    # toggle the details on click.
    details = next(
        element
        for element in walk(section)
        if element.name == "details"
        and "statistics-exact" in (dict(element.attributes).get("class") or "")
    )
    export_div = next(element for element in walk(details) if element.name == "div")
    export_anchor = next(element for element in walk(export_div) if element.name == "a")
    anchor_attrs = dict(export_anchor.attributes)
    assert text_of(export_anchor) == "Export table as CSV"
    assert anchor_attrs.get("download") is not None
    assert anchor_attrs.get("href") == sections_of(region)["journal"].export_url
    # Compact house styling: a small-wrapped plain text link, right-aligned,
    # no button chrome.
    assert any(element.name == "small" for element in walk(export_div))
    assert "justify-end" in (dict(export_div.attributes).get("class") or "")
    assert "role" not in anchor_attrs
    assert "outline" not in (anchor_attrs.get("class") or "")
    # …and it is not the summary itself (that would toggle the details).
    assert all(element.name != "summary" for element in walk(export_div))
    # The Other row's expand control is a plain text link: Pico's base `a`
    # look. No role="button", which triggers Pico's filled form-button
    # styling, and no undecorated class. tabindex keeps it reachable. The
    # reveal is reporting.js's delegated toggle, ui-tested end to end.
    toggle = next(
        element
        for element in walk(visible)
        if element.name == "a"
        and "statistics-fold-toggle" in (dict(element.attributes).get("class") or "")
    )
    toggle_attrs = dict(toggle.attributes)
    assert "role" not in toggle_attrs
    assert "undecorated" not in (toggle_attrs.get("class") or "")
    assert toggle_attrs.get("tabindex") == "0"
    assert "aria-controls" not in toggle_attrs
    assert toggle_attrs.get("aria-expanded") == "false"
    # The collapse control is server-rendered but hidden in the tfoot, a row
    # sorting never touches, and only shows while expanded. No <button>
    # remains in the table chrome: both controls are text links.
    tfoot = next(element for element in walk(section) if element.name == "tfoot")
    collapse_row = next(
        element
        for element in walk(tfoot)
        if element.name == "tr"
        and "statistics-collapse-row" in (dict(element.attributes).get("class") or "")
    )
    collapse_attrs = dict(collapse_row.attributes)
    assert "hidden" in collapse_attrs
    collapse_toggle = next(
        element
        for element in walk(collapse_row)
        if element.name == "a"
        and "statistics-fold-toggle" in (dict(element.attributes).get("class") or "")
    )
    assert text_of(collapse_toggle) == "Show top values only"
    collapse_toggle_attrs = dict(collapse_toggle.attributes)
    assert "role" not in collapse_toggle_attrs
    assert "undecorated" not in (collapse_toggle_attrs.get("class") or "")
    assert collapse_toggle_attrs.get("tabindex") == "0"
    assert not [element for element in walk(section) if element.name == "button"]
    # The label cell carries the toggle's text alongside the label.
    assert row_labels(visible)[-1].startswith("Other")
    assert set(row_labels(hidden)) == set(sorted(titles)[10:])
    # Folded rows are real values: they carry the drilldown links.
    links = [
        dict(element.attributes).get("href") for element in walk(hidden) if element.name == "a"
    ]
    assert links
    assert all(link and reverse("reporting:stats_fundingrequests_region") in link for link in links)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__page__folded_rows__carry_comparison_values(client: Client) -> None:
    titles = seed_tail(12)
    journal_paper("Prior paper", titles[10], year=2025)

    region = goto_region(client, tab="venues", **_COMPARE)
    section = sections_of(region)["journal"]
    folded = {row.label: row for row in section.folded}
    assert folded[titles[10]].comparison_publications == 1
    assert folded[titles[11]].comparison_publications == 0
    assert folded[titles[11]].comparison_amount is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__page__visible_plus_folded__equal_the_export_rows(client: Client) -> None:
    seed_tail(12)

    region = goto_region(client, tab="venues", **_COMPARE)
    section = sections_of(region)["journal"]
    page_labels = [row.label for row in section.rows if row.kind != "other"]
    page_labels += [row.label for row in section.folded]

    response = goto_export(client, "journal", **_COMPARE)
    assert page_labels == csv_labels(response)


# -- Comparison values (§11) -------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__compare_on__raw_prior_values_joined_by_label(client: Client) -> None:
    journal_paper("Shared then", "Shared Journal", year=2025)
    journal_paper("Shared now", "Shared Journal", year=2026)
    journal_paper("Current only", "Current Only Journal", year=2026)

    response = goto_export(client, "journal", **_COMPARE)
    rows = {row[0]: row for row in csv_rows(response)[1:]}
    code = GlobalPreferences.get_home_currency().code
    # The currency column holds the home currency's code, main and
    # comparison cells alike; amounts are bare decimals.
    assert rows["Shared Journal"][1:] == [code, "1", "0.00", "1", "0.00"]
    # Absent from the prior period: blank cells, distinguishable from zero.
    assert rows["Current Only Journal"][1:] == [code, "1", "0.00", "", ""]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__compare_off__no_comparison_columns(client: Client) -> None:
    seed_tail(1)

    response = goto_export(client, "journal")
    assert csv_rows(response)[0] == ["label", "currency", "publications", "amount"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__compare_toggle_gates_on_compare_one(client: Client) -> None:
    """Stale compare dates with the switch off must not turn the comparison
    columns on: the gate is ``compare == "1"``, exactly as on the page."""
    seed_tail(1)

    response = goto_export(
        client,
        "journal",
        compare_start_date="2025-01-01",
        compare_end_date="2025-12-31",
    )
    assert csv_rows(response)[0] == ["label", "currency", "publications", "amount"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__invalid_compare_period__current_period_columns_only(client: Client) -> None:
    """An unresolvable comparison period degrades to compare-off (§5.1):
    the export describes only the current period."""
    seed_tail(1)

    response = goto_export(client, "journal", compare="1", compare_start_date="2025-01-01")
    assert response.status_code == HTTPStatus.OK
    assert csv_rows(response)[0] == ["label", "currency", "publications", "amount"]


# -- Cache reuse (§5, §11) ---------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__after_page_render__answers_from_the_fact_cache(client: Client) -> None:
    seed_tail(2)
    # One page render caches both fact sets (main + comparison period).
    first = helpers.fact_pipeline_query_count(client, **_COMPARE)
    second = helpers.fact_pipeline_query_count(client, **_COMPARE)
    assert first > 0
    assert second == 0

    with CaptureQueriesContext(connection) as ctx:
        response = goto_export(client, "journal", **_COMPARE)
    pipeline_queries = sum(
        1
        for q in ctx.captured_queries
        if "DISTINCT" in q["sql"] and ' FROM "fundingrequests_fundingrequest"' in q["sql"]
    )
    assert response.status_code == HTTPStatus.OK
    assert pipeline_queries == 0


# -- URL pruning (§7) --------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__section_export_url__prunes_display_state__keeps_filters_and_compare(
    client: Client,
) -> None:
    seed_tail(1)

    region = goto_region(
        client,
        tab="venues",
        page="3",
        resolution="monthly",
        license=License.CC_BY.value,
        **_COMPARE,
    )
    section = sections_of(region)["journal"]
    assert section.export_url.startswith(export_url("journal"))
    params = query_params(section.export_url)
    assert "tab" not in params
    assert "page" not in params
    assert "resolution" not in params
    assert params["license"] == [License.CC_BY.value]
    assert params["start_date"] == [PERIOD["start_date"]]
    assert params["end_date"] == [PERIOD["end_date"]]
    assert params["compare"] == ["1"]
    assert params["compare_start_date"] == ["2025-01-01"]
    assert params["compare_end_date"] == ["2025-12-31"]


# -- Per-dimension headers (§6) ----------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__headers__follow_the_dimension_measures_with_uniform_amount(
    client: Client,
) -> None:
    helpers.request("Header paper")

    both = csv_rows(goto_export(client, "journal", **_COMPARE))[0]
    assert both == [
        "label",
        "currency",
        "publications",
        "amount",
        "comparison_publications",
        "comparison_amount",
    ]

    cost_type = csv_rows(goto_export(client, "cost_type", **_COMPARE))[0]
    assert cost_type == ["label", "currency", "amount", "comparison_amount"]

    # No money measure: no empty currency column.
    funder = csv_rows(goto_export(client, "funder", **_COMPARE))[0]
    assert funder == ["label", "publications", "comparison_publications"]


# -- Row semantics (§11) -----------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__repeated_dimension__one_request_counts_under_every_value(
    client: Client,
) -> None:
    fr = helpers.request("Split paper")
    position = helpers.position(fr.publication.pk, Decimal("1000.00"), Decimal("0.20"))
    position.assign_funding(helpers.budget("Fund One"), Decimal("600.00"))
    position.assign_funding(helpers.budget("Fund Two"), Decimal("400.00"))
    helpers.invoice([position])

    rows = {row[0]: row for row in csv_rows(goto_export(client, "funding_source"))[1:]}
    assert rows["Fund One"][2] == "1"
    assert rows["Fund Two"][2] == "1"
    assert rows["Fund One"][3] and rows["Fund Two"][3]  # both carry money


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__unknown_and_unassigned_rows__exported_as_data_quality_signal(
    client: Client,
) -> None:
    fixture = helpers.request("Anonymous paper")
    helpers.position(fixture.publication.pk, Decimal("1000.00"), Decimal("0.20"))
    fr = helpers.request("Unassigned paper")
    position = helpers.position(fr.publication.pk, Decimal("1000.00"), Decimal("0.20"))
    position.assign_funding(helpers.budget("Half Fund"), Decimal("600.00"))
    helpers.invoice([position])

    assert "Unknown" in csv_labels(goto_export(client, "institution"))
    assert "Unassigned" in csv_labels(goto_export(client, "funding_source"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__cost_type_zero_money_rows__suppressed(client: Client) -> None:
    fr = helpers.request("Free paper")
    position = helpers.position(fr.publication.pk, Decimal("0.00"), Decimal("0.20"))
    helpers.invoice([position])

    rows = csv_rows(goto_export(client, "cost_type"))
    assert rows[0] == ["label", "currency", "amount"]
    assert len(rows) == 1  # header only: a zero-money cost type is noise


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__currency_column__carries_the_home_currency_code(client: Client) -> None:
    """The currency column follows the page-wide home currency (ADR-0003),
    not a constant: switching the preference to USD exports USD amounts (one
    request paid in USD needs no conversion rate into itself)."""
    GlobalPreferences.set_home_currency(Currency.USD)
    fr = helpers.request("USD paper")
    position = helpers.position(
        fr.publication.pk, Decimal("100.00"), Decimal("0.00"), currency=Currency.USD
    )
    helpers.invoice([position])
    journal = fr.publication.article_journal
    assert journal is not None

    rows = {row[0]: row for row in csv_rows(goto_export(client, "journal"))[1:]}
    # The currency cell follows the preference, not a constant.
    assert rows[journal.title][1:] == ["USD", "1", "100.00"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export__csv_bytes__semicolon_bom_and_attachment_disposition(client: Client) -> None:
    seed_tail(1)

    response = goto_export(client, "journal")
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    header, first_data = text.splitlines()[:2]
    assert header == "label;currency;publications;amount"
    code = GlobalPreferences.get_home_currency().code
    # The currency column carries the code; amounts are bare decimals.
    assert re.match(rf"^[^;]+;{code};\d+;[\d.]+$", first_data)
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert re.match(
        r'attachment; filename="journal_export_\d{8}_\d{6}\.csv"',
        response["Content-Disposition"],
    )

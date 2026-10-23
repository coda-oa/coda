"""The statistics page and its HTMX list region (plan §3, §4, §8.5, §9).

``reporting_page`` answers, for the filtered set of funding requests: headline
row, then one section per §7 dimension with a plotly figure (json_script +
``reporting.js``), a table of exact values and drill-down links back into the
funding request list. The filter rail, chips and region mechanics are the
funding request list's own — reused through ``partials/filter_layout.html``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.forms import (
    FundingRequestListFilterForm,
    parse_label_ids,
)
from coda.apps.fundingrequests.models import Label
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Invoice
from coda.apps.listfilters import (
    ListRegionMixin,
    build_filter_summary,
    build_url,
    params_without,
)
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.reporting import queries
from coda.apps.reporting.dataset import build_facts
from coda.apps.reporting.drilldown import DrilldownLinks, list_view_url
from coda.apps.reporting.treemap import institution_treemap
from coda.contexts.statistics import charts
from coda.contexts.statistics.dimensions import DIMENSIONS, UNKNOWN
from coda.contexts.statistics.dto import (
    ChartSpec,
    GroupRow,
    Measure,
    RequestFact,
    StatisticsReport,
)
from coda.contexts.statistics.timeline import (
    TemporalResolution,
    temporal_counts,
    timeline_figure,
)

_PAGE_URL = "reporting:stats_fundingrequests"
_REGION_URL = "reporting:stats_fundingrequests_region"
_REGION_ELEMENT_ID = "reporting-region"


@dataclass(frozen=True)
class DimensionRow:
    """One row of a dimension's shared exact-value table; ``link`` filters the
    statistics page to the row's set (toggle off when already active), None
    when it cannot be expressed as list filters (Other/Unknown/Unassigned).
    ``comparison_publications``/``comparison_amount`` carry the previous
    period's values when the compare toggle is on, None otherwise."""

    label: str
    publications: int
    amount: Decimal | None
    link: str | None
    is_other: bool = False
    comparison_publications: int | None = None
    comparison_amount: Decimal | None = None
    #: Signed percentage change vs the comparison period, relative to the
    #: comparison value (e.g. 25 means +25%) — per measure, so each value
    #: cell annotates its own number. None when the comparison value is
    #: zero/absent (the cell renders "new") or compare is off.
    delta_publications_percent: Decimal | None = None
    delta_amount_percent: Decimal | None = None


@dataclass(frozen=True)
class MeasureColumn:
    """One value column of the shared table, with its total — or the ADR-0007
    note where the measure is non-additive and no total may be shown."""

    measure: Measure
    label: str
    total: Decimal | int | None
    note: str | None


@dataclass(frozen=True)
class IncompleteInvoice:
    """An invoice whose positions lacked a rate into the report currency; the
    currency-incomplete notice links to each one (plan §9, §10)."""

    pk: int
    number: str


@dataclass(frozen=True)
class ChartPanel:
    """One dimension's figure for ``reporting.js``: one dot per entity,
    publications on x, spend on y."""

    data_id: str
    title: str
    figure: dict[str, Any]


@dataclass(frozen=True)
class DimensionSection:
    """One section of the page: a dimension, its combined figure and one
    count-plus-spend table for the whole facet. ``value_count`` is the number
    of distinct values the facet produced (the "Other" fold counts once);
    ``unattributed`` the requests the facet could not express as a value —
    the data-quality signal in the section header."""

    dimension_id: str
    label: str
    chart: ChartPanel
    rows: tuple[DimensionRow, ...]
    columns: tuple[MeasureColumn, ...]
    value_count: int
    unattributed: int = 0


@breadcrumb("Funding Request Statistics", parent_url_name="reporting:home")
def reporting_page(request: HttpRequest) -> HttpResponse:
    """The page itself; a bare GET first gets the default period in its URL
    (§8.5), so the effective period is visible everywhere, drill-downs included."""
    if not request.GET.get("start_date") and not request.GET.get("end_date"):
        return redirect(_default_period_url(request))
    return render(request, "reporting/reporting.html", reporting_context(request))


if not settings.DEBUG:
    reporting_page = login_required(reporting_page)


class ReportingRegionView(ListRegionMixin, TemplateView):
    """The filter-driven region: the content re-renders on every sidebar
    change, and the sidebar itself swaps back out of band so its widgets keep
    the server-owned state (same mechanics as the funding request list). The
    ``tab`` parameter selects the content: ``overview`` (headline + timeline)
    or the dimension groups."""

    template_name = "reporting/partials/reporting_region.html"
    list_url_name = _PAGE_URL

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | reporting_context(self.request)


if not settings.DEBUG:
    reporting_region = login_required(ReportingRegionView.as_view())
else:
    reporting_region = ReportingRegionView.as_view()


def _prior_period(start: date, end: date) -> tuple[date, date] | None:
    """The window of the same length immediately before [start, end], or None
    for an unbounded range (a missing bound uses the date.min/max sentinels —
    "the same length before eternity" is not a window and would overflow)."""
    if start == date.min or end == date.max:
        return None
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


def reporting_context(request: HttpRequest) -> dict[str, Any]:
    """The whole page context: filtered facts -> report -> sections, plus the
    shared rail's form/chips state."""
    labels = list(Label.objects.all().order_by("name"))
    contracts = list(Contract.objects.all())
    vocabularies = GlobalPreferences.preloaded()
    filter_form = FundingRequestListFilterForm(
        request.GET, contracts=contracts, labels=labels, vocabularies=vocabularies
    )
    criteria, _sort_order = filter_form.search_criteria()
    # The home currency is page-wide (both periods convert into it); one
    # lookup serves both build_facts calls.
    home_currency = GlobalPreferences.get_home_currency()
    facts = build_facts(queries.fetch_requests(criteria), home_currency)
    compare = request.GET.get("compare") == "1" and filter_form.cleaned_data.get("date_range")
    # QueryDict.get returns the LAST value of a repeated key — exactly the
    # submitter-wins semantics the tab/resolution submit buttons rely on.
    tab = request.GET.get("tab", "overview")
    if tab not in ("overview", *(group.id for group in DIMENSION_GROUPS)):
        tab = "overview"
    try:
        resolution = TemporalResolution(request.GET.get("resolution", "weekly"))
    except ValueError:
        resolution = TemporalResolution.WEEKLY
    # The switch label names the prior window even when unchecked — the user
    # should see what "compare" would cover for the current date range. With
    # a one-sided range the prior window is undefined, not zero: compare
    # stays off (a one-sided window would otherwise render an all-zero
    # comparison).
    compare_period: tuple[date, date] | None = None
    if (date_range := filter_form.cleaned_data.get("date_range")) is not None:
        compare_period = _prior_period(date_range.start, date_range.end)
    compare = bool(compare and compare_period)
    comparison_facts: tuple[RequestFact, ...] = ()
    if compare:
        comparison_criteria = filter_form.search_criteria(date_override=compare_period)[0]
        comparison_facts = build_facts(queries.fetch_requests(comparison_criteria), home_currency)
    comparison_report = charts.report(comparison_facts, DIMENSIONS) if compare else None
    report = charts.report(facts, DIMENSIONS)

    date_errors = filter_form.errors.get("date_range")
    summary = build_filter_summary(
        request,
        labels,
        contracts,
        list_url_name=_PAGE_URL,
        region_url_name=_REGION_URL,
        included=filter_form.selected_label_ids,
        excluded=filter_form.excluded_label_ids,
        date_range=filter_form.cleaned_data.get("date_range"),
        date_range_error=str(date_errors[0]) if date_errors else None,
    )

    all_sections = _sections(
        report,
        DrilldownLinks.build(request, region_url_name=_REGION_URL, vocabularies=vocabularies),
        comparison=comparison_report,
    )
    treemap = institution_treemap(facts, Institution.objects.all())
    by_id = {section.dimension_id: section for section in all_sections}

    def group_sections(group: DimensionGroup) -> list[DimensionSection]:
        return [by_id[section_id] for section_id in group.section_ids if section_id in by_id]

    return {
        "filter_form": filter_form,
        "labels": labels,
        "contract_list": contracts,
        "label_state": sorted(parse_label_ids(request.GET.getlist("labels"))),
        "active_filters": summary.chips,
        # The band's chip row: without the date chips. The two date inputs sit
        # in the toolbar right there — a removable duplicate's close action
        # cannot win against the inputs' own serialization, so it only
        # confuses. The drawer's rail keeps its chips.
        "band_active_filters": [chip for chip in summary.chips if chip.kind != "date"],
        "filter_count": summary.count,
        "filter_clear_url": reverse(_PAGE_URL),
        "filter_list_id": _REGION_ELEMENT_ID,
        "list_view_url": list_view_url(request),
        "headline": (
            replace(report.headline, comparison=comparison_report.headline)
            if comparison_report
            else report.headline
        ),
        "timeline": timeline_figure(
            temporal_counts(facts, resolution),
            temporal_counts(comparison_facts, resolution) if comparison_facts else None,
            resolution=resolution,
        ),
        "resolution": resolution,
        "resolutions": list(TemporalResolution),
        "comparison": comparison_report,
        "compare": bool(comparison_report),
        # The switch label names the actual prior window, not a vague "previous".
        "compare_period": compare_period,
        "tab": tab,
        "incomplete_invoices": _incomplete_invoices(facts),
        # The full group list drives the tab nav; the active tab filters the
        # rendered sections only.
        "groups": [
            {
                "group": group,
                "treemap": treemap if group.has_treemap else None,
                "sections": group_sections(group) if tab == group.id else (),
            }
            for group in DIMENSION_GROUPS
            if group_sections(group) or (group.has_treemap and treemap)
        ],
        "active_group": tab,
        # Test-only: sections_by_id() reads this; templates render via the
        # per-group entries above.
        "sections": all_sections,
    }


def _default_period_url(request: HttpRequest) -> str:
    """Same URL, current calendar year as the period (§8.5): the redirect makes
    the effective period visible in the URL and in every drill-down link."""
    year = timezone.localdate().year
    params = params_without(request.GET, "page")
    params["start_date"] = date(year, 1, 1).isoformat()
    params["end_date"] = date(year, 12, 31).isoformat()
    return build_url(_PAGE_URL, params)


def _dimension_row(row: GroupRow, comparison: GroupRow | None, link: str | None) -> DimensionRow:
    """One table row, joined with its comparison-period counterpart.

    The delta is spend-based when both sides carry an amount, publications
    otherwise; it is signed relative to the comparison value and None when
    there is nothing to compare against (no counterpart, or a zero base —
    a row that did not exist last period renders "new", not a percentage).
    """
    comparison_publications = comparison.publications if comparison else 0
    comparison_amount = comparison.amount if comparison else None
    delta_publications: Decimal | None = None
    delta_amount: Decimal | None = None
    if row.amount is not None and comparison_amount:
        delta_amount = (row.amount - comparison_amount) / comparison_amount * 100
    if comparison_publications:
        delta_publications = (
            (Decimal(row.publications) - comparison_publications)
            / Decimal(comparison_publications)
            * 100
        )
    return DimensionRow(
        label=row.label,
        publications=row.publications,
        amount=row.amount,
        link=link,
        is_other=row.is_other,
        comparison_publications=comparison_publications,
        comparison_amount=comparison_amount,
        delta_publications_percent=delta_publications,
        delta_amount_percent=delta_amount,
    )


def _sections(
    report: StatisticsReport,
    links: DrilldownLinks,
    comparison: StatisticsReport | None = None,
) -> list[DimensionSection]:
    """Figure and shared table under their dimension, in registry order;
    dimensions without a non-empty grouping do not get an empty section.
    ``comparison`` carries the previous period's report when the compare
    toggle is on — its rows join by label into the delta columns."""
    specs = {spec.dimension_id: spec for spec in report.charts}
    comparison_specs = {spec.dimension_id: spec for spec in comparison.charts} if comparison else {}
    sections: list[DimensionSection] = []
    for dimension in DIMENSIONS:
        spec = specs.get(dimension.id)
        if spec is None:
            continue
        comparison_rows = (
            {row.label: row for row in comparison_specs[dimension.id].rows}
            if dimension.id in comparison_specs
            else {}
        )
        rows = tuple(
            _dimension_row(row, comparison_rows.get(row.label), links.link(dimension.id, row))
            for row in spec.rows
        )
        sections.append(
            DimensionSection(
                dimension_id=dimension.id,
                label=dimension.label,
                chart=_panel(spec, comparison_specs.get(dimension.id)),
                rows=rows,
                columns=tuple(
                    MeasureColumn(
                        measure=column.measure,
                        label=charts.MEASURE_LABELS[column.measure],
                        total=column.total,
                        note=column.note,
                    )
                    for column in spec.columns
                ),
                value_count=len(spec.rows),
                unattributed=sum(
                    row.publications
                    for row in spec.rows
                    if row.label in _UNATTRIBUTED_LABELS.get(dimension.id, ())
                ),
            )
        )
    return sections


def _panel(spec: ChartSpec, comparison: ChartSpec | None = None) -> ChartPanel:
    figure = spec.figure
    if comparison is not None:
        figure = charts.with_comparison(figure, spec, comparison)
    return ChartPanel(
        data_id=f"chart-{spec.dimension_id}",
        title=spec.title,
        figure=figure,
    )


#: The sentinel row labels marking requests a facet cannot attribute. Every
#: dimension's unknown value renders as the UNKNOWN sentinel string.
_UNATTRIBUTED_LABELS: dict[str, tuple[str, ...]] = {
    "institution": (UNKNOWN,),
    "subject_area": (UNKNOWN,),
    "publication_type": (UNKNOWN,),
    "publication_form": (UNKNOWN,),
    "license": (UNKNOWN,),
    "open_access_type": (UNKNOWN,),
    "journal": (UNKNOWN,),
    "publisher": (UNKNOWN,),
}


@dataclass(frozen=True)
class DimensionGroup:
    """A coherent view over the dimension sections: one chip in the jump nav,
    one band in the page grid. The group is a navigation/layout unit only —
    the sections render unchanged inside it."""

    id: str
    label: str
    section_ids: tuple[str, ...]
    has_treemap: bool = False


DIMENSION_GROUPS: tuple[DimensionGroup, ...] = (
    DimensionGroup(
        id="publication",
        label="Publication",
        section_ids=(
            "subject_area",
            "publication_type",
            "publication_form",
            "license",
            "open_access_type",
        ),
    ),
    DimensionGroup(id="venues", label="Venues", section_ids=("journal", "publisher")),
    DimensionGroup(
        id="cost",
        label="Cost & contracts",
        section_ids=("cost_type", "contract", "funding_source"),
    ),
    DimensionGroup(
        id="attribution",
        label="Attribution",
        section_ids=("institution", "funder"),
        has_treemap=True,
    ),
)


def _incomplete_invoices(facts: Sequence[RequestFact]) -> tuple[IncompleteInvoice, ...]:
    """The invoices behind the excluded amounts, deduplicated and ordered —
    the notice names the affected requests' invoices, not just their count."""
    ids = {invoice_id for fact in facts for invoice_id in fact.unconvertible_invoice_ids}
    if not ids:
        return ()
    return tuple(
        IncompleteInvoice(pk=invoice.pk, number=invoice.number)
        for invoice in Invoice.objects.filter(pk__in=ids).order_by("number")
    )

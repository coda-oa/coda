"""The statistics page and its HTMX list region (plan §3, §4, §8.5, §9).

``reporting_page`` answers, for the filtered set of funding requests: headline
row, then one section per §7 dimension with a plotly figure (json_script +
``reporting.js``), a table of exact values and drill-down links back into the
funding request list. The filter rail, chips and region mechanics are the
funding request list's own — reused through ``partials/filter_layout.html``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.filters import build_filter_summary
from coda.apps.fundingrequests.forms import FundingRequestListFilterForm
from coda.apps.fundingrequests.models import Label
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Invoice
from coda.apps.listfilters import ListRegionMixin, build_url, params_without
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.reporting import dataset, factcache, queries
from coda.apps.reporting.drilldown import DrilldownLinks, list_view_url
from coda.apps.reporting.treemap import institution_treemap
from coda.apps.widgets import DateRangeWidget
from coda.contexts.statistics import aggregation, charts
from coda.contexts.statistics.dimensions import DIMENSIONS, Dimension, by_id
from coda.contexts.statistics.dto import (
    ChartSpec,
    GroupRow,
    Measure,
    RequestFact,
    RowKind,
    StatisticsReport,
)
from coda.contexts.statistics.timeline import (
    TemporalResolution,
    temporal_counts,
    timeline_figure,
)
from coda.domain.date import DateRange, InvalidDateError, InvalidDateRangeError

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
    amount: Decimal
    link: str | None
    kind: RowKind = RowKind.VALUE
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
@login_required
@require_GET
def reporting_page(request: HttpRequest) -> HttpResponse:
    """The page itself; a bare GET first gets the default period in its URL
    (§8.5), so the effective period is visible everywhere, drill-downs included."""
    if not request.GET.get("start_date") and not request.GET.get("end_date"):
        return redirect(_default_period_url(request))
    return render(request, "reporting/reporting.html", reporting_context(request))


class ReportingRegionView(ListRegionMixin, TemplateView):
    """The filter-driven region: the content re-renders on every sidebar
    change, and the sidebar itself swaps back out of band so its widgets keep
    the server-owned state (same mechanics as the funding request list). The
    ``tab`` parameter selects the content: ``overview`` (headline + timeline)
    or the dimension groups."""

    template_name = "reporting/partials/reporting_region.html"
    list_url_name = _PAGE_URL

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs) | reporting_context(self.request)
        # The compare prefill's params, or None to push the request's own GET.
        # Stashed here because recomputing the context in _push_url just for
        # this key would run the form build and criteria pass twice per htmx
        # request.
        self._push_params: QueryDict | None = context.get("push_params")
        return context

    def _push_url(self) -> str:
        if self._push_params is None:
            return super()._push_url()
        return reverse(self.list_url_name, query=self._push_params)


reporting_region = login_required(ReportingRegionView.as_view())


def reporting_context(request: HttpRequest) -> dict[str, Any]:
    """The whole page context: filtered facts -> report -> sections, plus the
    shared rail's form/chips state.

    Computation is scoped to the active tab: the dimension report, its drill
    link tables and the comparison report cover only the active group's
    dimensions. The facts pipeline below them dominates the request cost,
    and every tab switch re-runs it anyway. Group *membership* (which tabs
    the nav shows) stays data-driven and tab-independent: a group whose
    dimensions the fact set never populates vanishes from the nav on every
    tab, exactly as before."""
    # The used-label set everywhere: a label attached to no request can never
    # match a criterion, so offering it only ever produces zero-result
    # filters (same set the list page's pills offer).
    labels = list(Label.used_labels())
    contracts = list(Contract.objects.all())
    vocabularies = GlobalPreferences.preloaded()
    # When compare is switched on with empty inputs, prefill them with the
    # same-length window before the selected range. The injected values then
    # render into the widgets and ride out via push_params, so URL and inputs
    # agree. An unbounded main range has no prior window, so no prefill and
    # compare resolves to nothing. The range is parsed directly because a
    # second form validation would pay the choice queries twice for one value.
    compare_data = request.GET.copy()
    compare_requested = request.GET.get("compare") == "1"
    prefill_window: DateRange | None = None
    push_params: QueryDict | None = None
    if compare_requested and (
        not request.GET.get("compare_start_date") and not request.GET.get("compare_end_date")
    ):
        try:
            prefill_source = DateRange.from_iso(
                start=request.GET.get("start_date"), end=request.GET.get("end_date")
            )
            prefill_window = prefill_source.prior_window()
        except (InvalidDateError, InvalidDateRangeError):
            prefill_window = None
        if prefill_window is not None:
            compare_data["compare_start_date"] = prefill_window.start.isoformat()
            compare_data["compare_end_date"] = prefill_window.end.isoformat()
            # request.GET is immutable, so the region view pushes these via
            # its push_params override instead of a mutated request.GET.
            push_params = compare_data
    filter_form = FundingRequestListFilterForm(
        compare_data,
        contracts=contracts,
        labels=labels,
        vocabularies=vocabularies,
        # No pill row on this page: the sidebar's visible include-labels
        # widget is the single writer of the `labels` param (labels is
        # set-valued and read as a union — a second writer would mask
        # removals).
        include_labels_widget=True,
    )
    # Disable the compare inputs server-side while compare is off, because
    # JS-only disabling leaves operable content invisible to screen readers
    # (WCAG 4.1.2).
    if not compare_requested:
        for subwidget in filter_form.fields["compare_range"].widget.widgets:
            subwidget.attrs["disabled"] = True
    filter_form.is_valid()  # fills cleaned_data for the comparison resolution below
    criteria, _sort_order = filter_form.search_criteria()
    # The home currency is page-wide (both periods convert into it); one
    # lookup serves both facts_for calls.
    home_currency = GlobalPreferences.get_home_currency()

    def build_facts(comparison: DateRange | None) -> tuple[RequestFact, ...]:
        if comparison is None:
            return dataset.build_facts(queries.fetch_requests(criteria), home_currency)
        comparison_criteria = filter_form.search_criteria(
            date_override=(comparison.start, comparison.end)
        )[0]
        return dataset.build_facts(queries.fetch_requests(comparison_criteria), home_currency)

    facts = factcache.facts_for(request.GET, home_currency, build_facts)
    # The comparison window is user-owned: the compare inputs carry it, and
    # the prefill above is only the default. Both bounds are required because
    # a missing bound would stretch the window to eternity. Invalid or
    # one-sided dates disable the comparison instead of failing the page, so
    # the rejected value stays visible in its input and the error renders
    # below the switch.
    comparison_period: DateRange | None = None
    comparison_error: str | None = None
    if compare_requested:
        if "compare_range" in filter_form.errors:
            comparison_error = str(filter_form.errors["compare_range"][0])
        else:
            compare_range = filter_form.cleaned_data.get("compare_range")
            main_range: DateRange | None = filter_form.cleaned_data.get("date_range")
            if compare_range is None or compare_range.is_unbounded():
                comparison_period = main_range.prior_window() if main_range is not None else None
            elif compare_range.start == date.min or compare_range.end == date.max:
                comparison_error = "Both comparison dates are required."
                # Because the view produced this error, compress never ran and
                # the inputs are not yet marked invalid — do it here so screen
                # readers can associate the message via aria-describedby.
                cast(DateRangeWidget, filter_form.fields["compare_range"].widget).mark_invalid()
            else:
                comparison_period = compare_range
    comparison_facts: tuple[RequestFact, ...] = ()
    if comparison_period:
        comparison_facts = factcache.facts_for(
            request.GET,
            home_currency,
            build_facts,
            comparison_period=comparison_period,
        )
    # QueryDict.get returns the LAST value of a repeated key — exactly the
    # submitter-wins semantics the tab/resolution submit buttons rely on.
    tab = request.GET.get("tab", "overview")
    if tab not in ("overview", *(group.id for group in DIMENSION_GROUPS)):
        tab = "overview"
    try:
        resolution = TemporalResolution(request.GET.get("resolution", "weekly"))
    except ValueError:
        resolution = TemporalResolution.WEEKLY

    active_group = next((group for group in DIMENSION_GROUPS if group.id == tab), None)
    active_dimensions = (
        tuple(by_id(section_id) for section_id in active_group.section_ids) if active_group else ()
    )
    comparison_report = (
        charts.report(comparison_facts, active_dimensions) if comparison_period else None
    )
    report = charts.report(facts, active_dimensions)

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

    sections = _sections(
        report,
        DrilldownLinks.build(
            request,
            region_url_name=_REGION_URL,
            vocabularies=vocabularies,
            lookups=_needed_lookups(active_dimensions),
        ),
        comparison=comparison_report,
    )
    # The treemap reads the whole fact set, not the active group's dimensions,
    # and costs ~4ms. It is computed unconditionally and shown on the group that owns
    # it. Its presence keeps the attribution tab in the nav even when the
    # institution section itself has no rows.
    treemap = institution_treemap(facts, Institution.objects.all())
    sections_by_id = {section.dimension_id: section for section in sections}

    def group_sections(group: DimensionGroup) -> list[DimensionSection]:
        return [
            sections_by_id[section_id]
            for section_id in group.section_ids
            if section_id in sections_by_id
        ]

    # Once per group: the nav filter and the value below would otherwise call
    # it twice per group.
    nav_sections = {group: group_sections(group) for group in DIMENSION_GROUPS}

    # The compare inputs re-render from the form's bound data, so a rejected
    # value stays visible in its input — the same contract as the sidebar's
    # date inputs.
    return {
        "filter_form": filter_form,
        # The compare params the region view should push; None pushes the
        # request's own GET.
        "push_params": push_params,
        "labels": labels,
        "contract_list": contracts,
        "filter_include_labels": filter_form.include_labels_widget,
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
        # The switch state follows the user's toggle, not the resolved window:
        # an invalid compare period keeps the inputs and error visible with
        # the switch still on. `compare` stays "a comparison actually
        # rendered", because the tables' delta and "new" badges annotate real
        # comparison values.
        "compare_on": compare_requested,
        "compare": bool(comparison_report),
        "comparison_period": (
            (comparison_period.start, comparison_period.end) if comparison_period else None
        ),
        "comparison_error": comparison_error,
        "tab": tab,
        "incomplete_invoices": _incomplete_invoices(facts),
        # The tab nav needs every surviving group; only the active one renders
        # its sections (the template loops groups and filters on the tab).
        # Membership is the cheap has_rows pass. Figures and link tables are
        # built only for the active group above.
        "groups": [
            {
                "group": group,
                "treemap": treemap if group.has_treemap else None,
                "sections": nav_sections[group] if tab == group.id else (),
            }
            for group in DIMENSION_GROUPS
            if nav_sections[group] or (group.has_treemap and treemap) or _has_rows(group, facts)
        ],
        "active_group": tab,
    }


def _default_period_url(request: HttpRequest) -> str:
    """Same URL, current calendar year as the period (§8.5): the redirect makes
    the effective period visible in the URL and in every drill-down link."""
    year = timezone.localdate().year
    params = params_without(request.GET, "page")
    params["start_date"] = date(year, 1, 1).isoformat()
    params["end_date"] = date(year, 12, 31).isoformat()
    return build_url(_PAGE_URL, params)


def _dimension_row(
    row: GroupRow, comparison: GroupRow | None, link: str | None, has_spend: bool
) -> DimensionRow:
    """One table row, joined with its comparison-period counterpart.

    The delta is spend-based when the dimension has a spend measure and both
    sides carry an amount, publications otherwise; it is signed relative to
    the comparison value and None when there is nothing to compare against
    (no counterpart, or a zero base — a row that did not exist last period
    renders "new", not a percentage).
    """
    comparison_publications = comparison.publications if comparison else 0
    comparison_amount = comparison.amount if comparison else None
    delta_publications: Decimal | None = None
    delta_amount: Decimal | None = None
    if has_spend and comparison_amount:
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
        kind=row.kind,
        comparison_publications=comparison_publications,
        comparison_amount=comparison_amount,
        delta_publications_percent=delta_publications,
        delta_amount_percent=delta_amount,
    )


def _sections(
    report: StatisticsReport,
    links: DrilldownLinks,
    comparison: StatisticsReport | None = None,
    comparison_label: str = "previous period",
) -> list[DimensionSection]:
    """Figure and shared table under their dimension, in registry order;
    dimensions without a non-empty grouping do not get an empty section.
    ``comparison`` carries the comparison period's report when compare is
    on, and its rows join by label into the delta columns."""
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
            _dimension_row(
                row,
                comparison_rows.get(row.label),
                links.link(dimension.id, row),
                has_spend=dimension.money is not None,
            )
            for row in spec.rows
        )
        sections.append(
            DimensionSection(
                dimension_id=dimension.id,
                label=dimension.label,
                chart=_panel(
                    spec, comparison_specs.get(dimension.id), comparison_label=comparison_label
                ),
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
                    row.publications for row in spec.rows if row.kind is RowKind.UNKNOWN
                ),
            )
        )
    return sections


def _panel(
    spec: ChartSpec,
    comparison: ChartSpec | None = None,
    comparison_label: str = "previous period",
) -> ChartPanel:
    figure = spec.figure
    if comparison is not None:
        figure = charts.with_comparison(figure, spec, comparison, comparison_label=comparison_label)
    return ChartPanel(
        data_id=f"chart-{spec.dimension_id}",
        title=spec.title,
        figure=figure,
    )


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


def _has_rows(group: DimensionGroup, facts: Sequence[RequestFact]) -> bool:
    """The cheap nav-membership test for one group: any of its dimensions
    would produce a chart row (first-contribution early exit, no figures)."""
    return aggregation.has_rows(
        facts,
        tuple(by_id(section_id) for section_id in group.section_ids),
    )


def _needed_lookups(dimensions: Sequence[Dimension]) -> tuple[str, ...]:
    """The drilldown lookup tables the rendered dimensions' facets name.
    Rows without a facet, or whose label already is the facet value
    (``identity``), resolve without a table."""
    return tuple(
        {
            dimension.facet.lookup
            for dimension in dimensions
            if dimension.facet is not None and not dimension.facet.identity
        }
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

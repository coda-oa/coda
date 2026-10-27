"""Groupings -> plotly figure JSON (plan §9).

Pure: takes Grouping values, returns the exact {data, layout, config} object
``Plotly.newPlot`` consumes, with one figure per dimension. Each figure shows
every measure of the dimension as its own colour-coded panel over the shared
entity axis, so counts and money stay directly comparable without sharing a
scale — and a server-side PDF renderer can reuse the same figures (plan §13).
Exact values are NOT here — the template renders the section table.
"""

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import plotly.graph_objects as go

from coda.contexts.statistics.aggregation import DEFAULT_TOP_N, group_by
from coda.contexts.statistics.dimensions import ZERO, Dimension
from coda.contexts.statistics.dto import (
    ChartSpec,
    ColumnSpec,
    Grouping,
    GroupRow,
    Headline,
    Measure,
    RequestFact,
    StatisticsReport,
)

MEASURE_LABELS: dict[Measure, str] = {
    Measure.PUBLICATIONS: "publications",
    Measure.PAID_OUT: "spend incl. tax",
    Measure.FUNDED_BY: "funded by incl. tax",
}

#: Okabe–Ito hues — colour-blind safe, one per measure.
MEASURE_COLORS: dict[Measure, str] = {
    Measure.PUBLICATIONS: "#0072B2",
    Measure.PAID_OUT: "#E69F00",
    Measure.FUNDED_BY: "#D55E00",
}

NON_ADDITIVE_NOTE = (
    "Totals for this column count each request once, so entities sharing a "
    "request are double-counted — sum the rows for a grand total."
)


def build_figure(grouping: Grouping) -> dict[str, Any]:
    """Vertical columns: one full-width panel per measure, stacked, the entity
    names under the columns on the shared X axis (rendered once, under the
    bottom panel). The figure width never depends on label length, so sections
    don't jump horizontally when filters change. Long names rotate 45°, the
    exact value sits at each column tip, and the value scale keeps headroom
    for those labels."""
    measures = grouping.measures
    domains = [[0.0, 1.0]] if len(measures) == 1 else [[0.0, 0.45], [0.55, 1.0]]
    figure = go.Figure()
    axes: dict[str, Any] = {}
    annotations: list[dict[str, Any]] = []
    for index, measure in enumerate(measures):
        values = [_row_value(row, measure) for row in grouping.rows]
        figure.add_trace(
            go.Bar(
                x=[row.label for row in grouping.rows],
                y=values,
                name=MEASURE_LABELS[measure],
                marker_color=MEASURE_COLORS[measure],
                yaxis="y" if index == 0 else f"y{index + 1}",
                text=[_bar_label(measure, value) for value in values],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
            )
        )
        axis_name = "yaxis" if index == 0 else f"yaxis{index + 1}"
        axes[axis_name] = {
            "domain": domains[index],
            "tickformat": _tick_format(measure),
            # All-zero data must not autorange below zero.
            "range": [
                0,
                _label_headroom(measure, max(values)) if max(values, default=0) > 0 else 1,
            ],
        }
        # Axis titles of stacked panels would overlap at the shared left edge;
        # a paper annotation above each panel names it in reading direction.
        annotations.append(
            {
                "x": 0,
                "xref": "paper",
                "xanchor": "left",
                "y": domains[index][1] - 0.012,
                "yref": "paper",
                "yanchor": "bottom",
                "text": MEASURE_LABELS[measure],
                "showarrow": False,
                "font": {"size": 12},
            }
        )
    # Cap the rendered bar thickness: with few categories plotly stretches
    # each bar over its whole slot (a one-row figure draws a 1100px bar).
    # bargap is the empty fraction of a slot, so a slot of slot_px px yields
    # bars of (1 - bargap) * slot_px px.
    MAX_BAR_PX = 90
    TYPICAL_PLOT_PX = 1100  # typical plot width; bargap only needs to be close
    rows = len(grouping.rows)
    bargap = max(0.3, 1.0 - MAX_BAR_PX / (TYPICAL_PLOT_PX / max(rows, 1)))
    # The plot area — not the figure — is the fixed quantity: the rotated
    # label band gets its own margin sized from the longest label, so
    # tick-label length changes figure height but never squeezes the chart.
    # Single-measure figures render one panel, so they get half the plot.
    PLOT_HEIGHT = 330  # px of combined bar panels (two-measure figures)
    TOP_MARGIN = 22  # px, holds the topmost panel's label
    plot = PLOT_HEIGHT if len(measures) > 1 else PLOT_HEIGHT // 2
    label_band = _label_band_px([row.label for row in grouping.rows])
    figure.update_layout(
        **axes,
        xaxis={
            "automargin": False,
            "tickangle": -45,
            "type": "category",
            "domain": [0.0, 1.0],
        },
        height=plot + label_band + TOP_MARGIN,
        bargap=bargap,
        annotations=annotations,
        showlegend=False,
        margin={"l": 10, "r": 10, "t": TOP_MARGIN, "b": label_band},
    )
    json: dict[str, Any] = figure.to_plotly_json()
    return json


def _label_band_px(labels: Sequence[str]) -> int:
    """Bottom margin for the -45° tick labels, from the longest one.

    At -45° a label of L px rendered width needs about L·sin(45°) ≈ 0.7·L of
    vertical band. 7px per character is close enough for system-ui 12px; the
    14px base covers the axis line and tick marks.
    """
    longest = max((len(label) for label in labels), default=0)
    return 14 + int(longest * 7 * 0.7)


def report(
    facts: Sequence[RequestFact],
    dimensions: Sequence[Dimension],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> StatisticsReport:
    """Headline plus one figure per dimension; dimensions without data omit
    their section entirely."""
    charts: list[ChartSpec] = []
    for dimension in dimensions:
        grouping = group_by(facts, dimension, top_n=top_n)
        if not grouping.rows:
            continue
        charts.append(
            ChartSpec(
                dimension_id=dimension.id,
                title=_title(dimension.label, grouping.measures),
                columns=tuple(
                    ColumnSpec(
                        measure=measure,
                        total=grouping.total(measure),
                        note=(None if measure not in grouping.non_additive else NON_ADDITIVE_NOTE),
                    )
                    for measure in grouping.measures
                ),
                rows=grouping.rows,
                figure=build_figure(grouping),
            )
        )
    return StatisticsReport(headline=_headline(facts), charts=tuple(charts))


def _title(dimension_label: str, measures: tuple[Measure, ...]) -> str:
    return f"{dimension_label} — {' & '.join(MEASURE_LABELS[m] for m in measures)}"


def _bar_label(measure: Measure, value: float) -> str:
    """The exact value at the bar tip, compact. Money rounds UP to k€, so a
    label never understates what was spent; the exact figure is in the table
    below the chart."""
    if not value:
        return ""  # no label on zero-height bars: nothing to annotate
    if measure is Measure.PUBLICATIONS:
        return f"{value:,}"
    thousands = float(value) / 1000
    rounded = math.ceil(round(thousands, 6))
    return f"{rounded:,.0f} k€"


def _label_headroom(measure: Measure, max_value: float) -> float:
    """X-range so the outside label at the longest bar still fits."""
    headroom = 1.18 if measure is Measure.PUBLICATIONS else 1.30
    return max_value * headroom


def _tick_format(measure: Measure) -> str:
    """SI ticks (50k, 150k) for money; plain numbers for counts."""
    return "~s" if measure is not Measure.PUBLICATIONS else ","


def _row_value(row: GroupRow, measure: Measure) -> int | float:
    if measure is Measure.PUBLICATIONS:
        return row.publications
    return float(row.amount)


def _headline(facts: Sequence[RequestFact]) -> Headline:
    spend = sum((fact.paid_out_total for fact in facts), ZERO)
    publications = len(facts)
    avg = spend / publications if publications else None
    # Concentration: the five highest individual request spends' share of
    # total spend — dimension-free, computable from the fact set alone.
    top5_share: Decimal | None = None
    if spend:
        top5 = sum(sorted((fact.paid_out_total for fact in facts), reverse=True)[:5], ZERO)
        top5_share = top5 / spend * 100 if spend else None
    return Headline(
        publications=publications,
        spend=spend,
        requests_without_invoice=sum(1 for fact in facts if not fact.has_invoice),
        requests_unconvertible=sum(1 for fact in facts if fact.invoices_without_rate > 0),
        avg_per_request=avg,
        top5_share=top5_share,
    )


#: Muted variant of a measure color for the comparison series — same hue,
#: washed out, so "then" reads as background to "now".
def _muted(color: str) -> str:
    return color + "66"  # 40% alpha over the panel background


def with_comparison(
    figure: dict[str, Any],
    spec: ChartSpec,
    comparison: ChartSpec,
) -> dict[str, Any]:
    """Augment a bars figure with the comparison period's series.

    One grouped pair per measure panel: the current series keeps its color
    and tip labels; the comparison series renders muted and unlabeled (the
    exact values live in the table's delta column). ``barmode: group`` is
    the correct encoding — current and previous are two series of the same
    measure over the same categories; stacking would claim they sum, and
    overlaying would hide one behind the other. Non-bar figures pass
    through unchanged (the treemap is out of scope for comparison).
    """
    if not spec.rows or not figure.get("data"):
        return figure
    if any(trace.get("type") != "bar" for trace in figure["data"]):
        return figure

    comparison_rows = {row.label: row for row in comparison.rows}
    measures = spec.columns
    data = list(figure["data"])
    # Traces are in measure order (one per panel); insert each comparison
    # series directly BEFORE its current-series twin: within a grouped pair,
    # plotly draws traces left-to-right in trace order, and "previous" reads
    # first (earlier in time) then "current".
    augmented: list[dict[str, Any]] = []
    for index, trace in enumerate(data):
        measure = measures[index].measure if index < len(measures) else None
        if measure is not None:
            values = [
                _row_value(comparison_rows[row.label], measure)
                if row.label in comparison_rows
                else 0
                for row in spec.rows
            ]
            augmented.append(
                {
                    "type": "bar",
                    "x": [row.label for row in spec.rows],
                    "y": values,
                    "name": f"previous — {MEASURE_LABELS[measure]}",
                    "marker": {"color": _muted(MEASURE_COLORS[measure])},
                    "yaxis": trace.get("yaxis", "y"),
                    "hovertemplate": "%{x}: %{y:,.2f}<extra>previous period</extra>",
                    "showlegend": True,
                }
            )
        augmented.append(trace)

    # The legend lives OUTSIDE the plot area, in a top margin band sized to
    # hold it: margin.t = legend band (~34px) + panel annotation (~16px) +
    # breathing room. With y=1.02/yanchor bottom the legend's top edge sits
    # just above the plot area's top; the annotations sit below it, inside
    # their panels.
    LEGEND_BAND = 52
    layout = {
        **figure["layout"],
        "barmode": "group",
        "bargap": 0.25,
        "bargroupgap": 0.05,
        "showlegend": True,
        "legend": {
            "orientation": "h",
            # Right-aligned above the plot area: the panel labels anchor left,
            # so the legend keeps to the free right side of the top band.
            "xanchor": "right",
            "x": 1.0,
            "yanchor": "bottom",
            "y": 1.0,
            "font": {"size": 11},
        },
        "margin": {**figure["layout"].get("margin", {}), "t": LEGEND_BAND},
    }
    return {**figure, "data": augmented, "layout": layout}

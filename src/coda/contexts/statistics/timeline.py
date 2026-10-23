"""Timeline request counts at multiple temporal resolutions (DASHBOARD.md §timeline).

Pure: takes RequestFact values and returns one point per bucket (week, month
or quarter) between the earliest and latest request date, zero-filled — a gap
in the data is an empty bucket, not a missing column. Weeks are ISO weeks
(Monday-based); the point's ``bucket_start`` is the value the chart renders
as the tick.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from coda.contexts.statistics.dto import RequestFact


class TemporalResolution(StrEnum):
    """How the timeline buckets request dates."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    """One bucket of the timeline: its first day and the number of funding
    requests whose request_date falls into that bucket."""

    bucket_start: datetime.date
    count: int


def _monday_of(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def _month_start(day: datetime.date) -> datetime.date:
    return day.replace(day=1)


def _quarter_start(day: datetime.date) -> datetime.date:
    return day.replace(day=1, month=(day.month - 1) // 3 * 3 + 1)


def _bucket_start(day: datetime.date, resolution: TemporalResolution) -> datetime.date:
    match resolution:
        case TemporalResolution.WEEKLY:
            return _monday_of(day)
        case TemporalResolution.MONTHLY:
            return _month_start(day)
        case TemporalResolution.QUARTERLY:
            return _quarter_start(day)


def _next_bucket_start(bucket: datetime.date, resolution: TemporalResolution) -> datetime.date:
    match resolution:
        case TemporalResolution.WEEKLY:
            return bucket + datetime.timedelta(days=7)
        case TemporalResolution.MONTHLY:
            year, month = bucket.year, bucket.month + 1
            if month > 12:
                year, month = year + 1, 1
            return bucket.replace(year=year, month=month)
        case TemporalResolution.QUARTERLY:
            year, month = bucket.year, bucket.month + 3
            if month > 12:
                year, month = year + 1, month - 12
            return bucket.replace(year=year, month=month)


def temporal_counts(
    facts: Sequence[RequestFact], resolution: TemporalResolution
) -> list[TimelinePoint]:
    """One TimelinePoint per bucket spanning the facts' request dates.

    Facts always carry a request date (the dataset fills it from the
    request); the None guard keeps the pure layer total.
    """
    dated = [fact.request_date for fact in facts if fact.request_date is not None]
    if not dated:
        return []
    first = _bucket_start(min(dated), resolution)
    last = _bucket_start(max(dated), resolution)
    counts: dict[datetime.date, int] = {}
    for day in dated:
        bucket = _bucket_start(day, resolution)
        counts[bucket] = counts.get(bucket, 0) + 1

    points: list[TimelinePoint] = []
    bucket = first
    while bucket <= last:
        points.append(TimelinePoint(bucket_start=bucket, count=counts.get(bucket, 0)))
        bucket = _next_bucket_start(bucket, resolution)
    return points


def _tick_angle(resolution: TemporalResolution, buckets: int) -> int:
    """Long labels rotate; short ones (months, quarters) read horizontal."""
    if resolution is TemporalResolution.WEEKLY:
        return -45
    return 0 if buckets <= 36 else -45


def _bucket_label(bucket: datetime.date, resolution: TemporalResolution) -> str:
    match resolution:
        case TemporalResolution.WEEKLY:
            return bucket.isoformat()
        case TemporalResolution.MONTHLY:
            return bucket.strftime("%Y-%m")
        case TemporalResolution.QUARTERLY:
            return f"{bucket.year}-Q{(bucket.month - 1) // 3 + 1}"


def timeline_figure(
    points: Sequence[TimelinePoint],
    comparison: Sequence[TimelinePoint] | None = None,
    *,
    resolution: TemporalResolution = TemporalResolution.WEEKLY,
) -> dict[str, object]:
    """The plotly figure JSON for the timeline: one bar per bucket.

    Follows the charts module's contract — {data, layout, config} exactly as
    ``Plotly.newPlot`` consumes it. The x axis is categorical (the buckets'
    first days) so nothing interpolates between buckets; the bucket count
    scales the figure height like the other figures do.

    With ``comparison`` (the prior period's counts), the axis extends over
    the union of both periods' buckets in one chart: the previous period
    renders muted (the charts module's washed-out convention) over its own
    buckets, the current period in full hue over its buckets. The two
    periods' buckets never overlap (the prior window ends before the current
    one starts), so every category carries exactly one bar; the legend names
    the two series.
    """
    if not points:
        return {"data": [], "layout": {"height": 160}, "config": {"responsive": True}}
    if comparison:
        buckets = sorted({p.bucket_start for p in points} | {p.bucket_start for p in comparison})
        x = [_bucket_label(bucket, resolution) for bucket in buckets]
        current_by_bucket = {p.bucket_start: p.count for p in points}
        comparison_by_bucket = {p.bucket_start: p.count for p in comparison}
        max_count = max(
            max(p.count for p in points),
            max((p.count for p in comparison), default=0),
        )
        data: list[dict[str, object]] = [
            {
                "type": "bar",
                "x": x,
                "y": [comparison_by_bucket.get(bucket, 0) for bucket in buckets],
                "name": "previous period",
                "marker": {"color": "#0072B266"},
                "hovertemplate": "%{x}: %{y} request(s)<extra>previous period</extra>",
                "showlegend": True,
            },
            {
                "type": "bar",
                "x": x,
                "y": [current_by_bucket.get(bucket, 0) for bucket in buckets],
                "name": "current period",
                "marker": {"color": "#0072B2"},
                "hovertemplate": "%{x}: %{y} request(s)<extra></extra>",
                "showlegend": True,
            },
        ]
        layout = {
            "height": 200,
            "margin": {"l": 40, "r": 10, "t": 34, "b": 30},
            "xaxis": {
                "type": "category",
                "tickangle": _tick_angle(resolution, len(buckets)),
                "automargin": True,
                "nticks": min(len(buckets), 26),
            },
            "yaxis": {
                "title": {"text": "requests / period"},
                "rangemode": "nonnegative",
                "range": [0, max_count * 1.15] if max_count else [0, 1],
            },
            "bargap": 0.15,
            # Legend above the plot area, right-aligned into the free side.
            "showlegend": True,
            "legend": {
                "orientation": "h",
                "xanchor": "right",
                "x": 1.0,
                "yanchor": "bottom",
                "y": 1.0,
                "font": {"size": 11},
            },
        }
    else:
        data = [
            {
                "type": "bar",
                "x": [_bucket_label(p.bucket_start, resolution) for p in points],
                "y": [p.count for p in points],
                "name": "current period",
                "marker": {"color": "#0072B2"},
                "hovertemplate": "%{x}: %{y} request(s)<extra></extra>",
                "showlegend": False,
            }
        ]
        max_count = max(p.count for p in points)
        layout = {
            "height": 180,
            "margin": {"l": 40, "r": 10, "t": 10, "b": 30},
            "xaxis": {
                "type": "category",
                "tickangle": _tick_angle(resolution, len(points)),
                "automargin": True,
                "nticks": min(len(points), 26),
            },
            "yaxis": {
                "title": {"text": "requests / period"},
                "rangemode": "nonnegative",
                "range": [0, max_count * 1.15] if max_count else [0, 1],
            },
            "bargap": 0.15,
            "showlegend": False,
        }
    return {"data": data, "layout": layout, "config": {"responsive": True}}

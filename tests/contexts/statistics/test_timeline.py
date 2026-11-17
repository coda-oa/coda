import datetime

from tests.contexts.statistics.factories import make_fact

from coda.contexts.statistics.timeline import (
    TemporalResolution,
    temporal_counts,
    timeline_figure,
)


def test__temporal_counts__weekly_buckets_by_monday() -> None:
    points = temporal_counts(
        [make_fact(), make_fact(request_date=datetime.date(2026, 5, 4))],
        TemporalResolution.WEEKLY,
    )

    # 2026-05-01 is a Friday of the week starting 04-27; 05-04 starts the next.
    assert [(p.bucket_start, p.count) for p in points] == [
        (datetime.date(2026, 4, 27), 1),
        (datetime.date(2026, 5, 4), 1),
    ]


def test__temporal_counts__monthly_buckets_by_first_of_month() -> None:
    points = temporal_counts(
        [
            make_fact(request_date=datetime.date(2026, 4, 29)),
            make_fact(request_date=datetime.date(2026, 5, 4)),
            make_fact(request_date=datetime.date(2026, 5, 20)),
        ],
        TemporalResolution.MONTHLY,
    )

    assert [(p.bucket_start, p.count) for p in points] == [
        (datetime.date(2026, 4, 1), 1),
        (datetime.date(2026, 5, 1), 2),
    ]


def test__temporal_counts__quarterly_buckets_by_quarter_start() -> None:
    points = temporal_counts(
        [
            make_fact(request_date=datetime.date(2026, 1, 15)),
            make_fact(request_date=datetime.date(2026, 3, 30)),
            make_fact(request_date=datetime.date(2026, 4, 2)),
        ],
        TemporalResolution.QUARTERLY,
    )

    assert [(p.bucket_start, p.count) for p in points] == [
        (datetime.date(2026, 1, 1), 2),
        (datetime.date(2026, 4, 1), 1),
    ]


def test__temporal_counts__zero_fills_gap_buckets() -> None:
    points = temporal_counts(
        [
            make_fact(request_date=datetime.date(2026, 1, 15)),
            make_fact(request_date=datetime.date(2026, 3, 15)),
        ],
        TemporalResolution.MONTHLY,
    )

    assert [p.count for p in points] == [1, 0, 1]  # February is a gap


def test__temporal_counts__empty_facts_yields_no_points() -> None:
    assert temporal_counts([], TemporalResolution.WEEKLY) == []


def test__timeline__labels_follow_the_resolution() -> None:
    points = temporal_counts(
        [make_fact(request_date=datetime.date(2026, 5, 4))],
        TemporalResolution.MONTHLY,
    )

    figure = timeline_figure(points, resolution=TemporalResolution.MONTHLY)

    assert figure["data"][0]["x"] == ["2026-05"]


def test__timeline__quarterly_labels_carry_the_quarter() -> None:
    points = temporal_counts(
        [make_fact(request_date=datetime.date(2026, 5, 4))],
        TemporalResolution.QUARTERLY,
    )

    figure = timeline_figure(points, resolution=TemporalResolution.QUARTERLY)

    assert figure["data"][0]["x"] == ["2026-Q2"]


def test__timeline__comparison_extends_axis_over_both_periods() -> None:
    current = temporal_counts(
        [make_fact(request_date=datetime.date(2026, 5, 4))], TemporalResolution.MONTHLY
    )
    previous = temporal_counts(
        [make_fact(request_date=datetime.date(2025, 5, 4))], TemporalResolution.MONTHLY
    )

    figure = timeline_figure(current, previous, resolution=TemporalResolution.MONTHLY)

    previous_trace, current_trace = figure["data"]
    assert previous_trace["x"] == current_trace["x"] == ["2025-05", "2026-05"]
    assert previous_trace["y"] == [1, 0]
    assert current_trace["y"] == [0, 1]

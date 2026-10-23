from decimal import Decimal

from tests.contexts.statistics.factories import institution, make_fact

from coda.contexts.statistics import dimensions
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.charts import (
    MEASURE_LABELS,
    NON_ADDITIVE_NOTE,
    build_figure,
    report,
)
from coda.contexts.statistics.dto import Measure, StatisticsReport

PUBLISHER_FACTS = (
    make_fact(publisher="Elsevier", paid_out_total=Decimal("100.00")),
    make_fact(publisher="Elsevier", paid_out_total=Decimal("50.00")),
    make_fact(publisher="Springer", paid_out_total=Decimal("20.00")),
)


def _charts_by_id(the_report: StatisticsReport) -> dict[str, object]:
    return {c.dimension_id: c for c in the_report.charts}


def test__report__builds_bars_with_both_measures() -> None:
    grouping = group_by(PUBLISHER_FACTS, dimensions.by_id("publisher"))

    figure = build_figure(grouping)

    assert [trace["type"] for trace in figure["data"]] == ["bar", "bar"]
    # One panel per measure over the shared category axis, in table row order.
    publications, spend = figure["data"]
    assert [row.label for row in grouping.rows] == ["Elsevier", "Springer"]
    assert [float(v) for v in publications["y"]] == [2.0, 1.0]
    assert [float(v) for v in spend["y"]] == [150.0, 20.0]
    # Separate value axes, one per measure, titled by panel annotation.
    layout = figure["layout"]
    assert [a["text"] for a in layout["annotations"]] == [
        MEASURE_LABELS[Measure.PUBLICATIONS],
        MEASURE_LABELS[Measure.PAID_OUT],
    ]
    assert not layout["showlegend"]


def test__report__titles_name_the_dimension_and_its_measures() -> None:
    the_report = report(PUBLISHER_FACTS, (dimensions.by_id("publisher"),))

    chart = _charts_by_id(the_report)["publisher"]

    assert chart.title == "Publisher — publications & spend incl. tax"  # type: ignore[attr-defined]


def test__report__single_measure_dimensions_get_a_single_full_width_panel() -> None:
    facts = (
        make_fact(
            publisher="Elsevier",
            paid_out_by_cost_type={"apc": Decimal("100.00")},
            paid_out_total=Decimal("100.00"),
            funders=("DFG",),
        ),
    )

    by_id = _charts_by_id(report(facts, dimensions.DIMENSIONS))

    assert [c.measure for c in by_id["cost_type"].columns] == [Measure.PAID_OUT]  # type: ignore[attr-defined]
    assert len(by_id["cost_type"].figure["data"]) == 1  # type: ignore[attr-defined]
    assert "yaxis2" not in by_id["cost_type"].figure["layout"]  # type: ignore[attr-defined]
    assert [c.measure for c in by_id["funder"].columns] == [Measure.PUBLICATIONS]  # type: ignore[attr-defined]
    assert all(
        trace["type"] == "bar"
        for chart in by_id.values()
        for trace in chart.figure["data"]  # type: ignore[attr-defined]
    )


def test__report__marks_non_additive_columns_and_hides_their_totals() -> None:
    facts = (
        make_fact(
            institutions=(institution("TU Berlin"), institution("Humboldt")),
            paid_out_total=Decimal("100.00"),
        ),
    )

    columns = _charts_by_id(report(facts, (dimensions.by_id("institution"),)))[
        "institution"
    ].columns  # type: ignore[attr-defined]
    assert columns
    assert all(c.note == NON_ADDITIVE_NOTE and c.total is None for c in columns)

    publisher_columns = _charts_by_id(report(PUBLISHER_FACTS, (dimensions.by_id("publisher"),)))[
        "publisher"
    ].columns  # type: ignore[attr-defined]
    assert publisher_columns
    assert all(c.note is None and c.total is not None for c in publisher_columns)


def test__report__headline_counts_publications_spend_and_gaps() -> None:
    facts = (
        make_fact(paid_out_total=Decimal("100.00"), has_invoice=True),
        make_fact(paid_out_total=Decimal("50.00"), has_invoice=False),
        make_fact(paid_out_total=Decimal(0), has_invoice=True, invoices_without_rate=2),
    )

    headline = report(facts, dimensions.DIMENSIONS).headline

    assert headline.publications == 3
    assert headline.spend == Decimal("150.00")
    assert headline.requests_without_invoice == 1
    assert headline.requests_unconvertible == 1


def test__report__on_empty_facts_yields_no_charts_and_a_zero_headline() -> None:
    the_report = report((), dimensions.DIMENSIONS)

    assert the_report.charts == ()
    assert the_report.headline.publications == 0
    assert the_report.headline.spend == Decimal(0)

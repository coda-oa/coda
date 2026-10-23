from decimal import Decimal

import pytest
from tests.contexts.statistics.factories import institution, make_fact, source

from coda.contexts.statistics import dimensions
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.dto import ContractRef, Measure


def test__group_by_publisher__carries_both_measures_on_every_row() -> None:
    facts = (
        make_fact(publisher="Elsevier", paid_out_total=Decimal("100.00")),
        make_fact(publisher="Elsevier", paid_out_total=Decimal("50.00")),
        make_fact(publisher="Springer", paid_out_total=Decimal("20.00")),
    )

    grouping = group_by(facts, dimensions.by_id("publisher"))

    assert [(r.label, r.publications, r.amount) for r in grouping.rows] == [
        ("Elsevier", 2, Decimal("150.00")),
        ("Springer", 1, Decimal("20.00")),
    ]
    assert grouping.non_additive == frozenset()
    assert grouping.total(Measure.PUBLICATIONS) == 3
    assert grouping.total(Measure.PAID_OUT) == Decimal("170.00")


def test__group_by__money_leads_the_ranking() -> None:
    """Funded-but-unpaid entities must never push paid-out ones off the visible
    top; their row keeps the real count and a zero amount the template dashes."""
    facts = (
        make_fact(publisher="Elsevier", paid_out_total=Decimal("100.00")),
        make_fact(publisher="Small Press", paid_out_total=Decimal("50.00")),
        make_fact(publisher="Unpaid Press", paid_out_total=Decimal("0.00")),
    )

    grouping = group_by(facts, dimensions.by_id("publisher"))

    assert [(r.label, r.publications, r.amount) for r in grouping.rows] == [
        ("Elsevier", 1, Decimal("100.00")),
        ("Small Press", 1, Decimal("50.00")),
        ("Unpaid Press", 1, Decimal("0.00")),
    ]
    assert grouping.total(Measure.PAID_OUT) == Decimal("150.00")


def test__group_by_repeated_dimension__counts_the_request_in_full_under_every_value() -> None:
    facts = (
        make_fact(
            institutions=(institution("TU Berlin"), institution("Humboldt University")),
            paid_out_total=Decimal("100.00"),
        ),
    )

    grouping = group_by(facts, dimensions.by_id("institution"))

    assert [(r.label, r.publications, r.amount) for r in grouping.rows] == [
        ("Humboldt University", 1, Decimal("100.00")),
        ("TU Berlin", 1, Decimal("100.00")),
    ]
    assert grouping.non_additive == frozenset({Measure.PUBLICATIONS, Measure.PAID_OUT})
    assert grouping.total(Measure.PUBLICATIONS) is None
    assert grouping.total(Measure.PAID_OUT) is None


def test__group_by_single_dimension__groups_a_missing_value_as_unknown() -> None:
    facts = (
        make_fact(publisher="Elsevier", paid_out_total=Decimal("20.00")),
        make_fact(publisher=None, paid_out_total=Decimal("10.00")),
    )

    grouping = group_by(facts, dimensions.by_id("publisher"))

    assert [(r.label, r.publications, r.is_unknown) for r in grouping.rows] == [
        ("Elsevier", 1, False),
        ("Unknown", 1, True),
    ]


@pytest.mark.parametrize("dimension_id", ["subject_area", "publication_type"])
def test__group_by_concept_dimension__groups_a_blank_concept_name_as_unknown(
    dimension_id: str,
) -> None:
    """The default row of these non-nullable concepts carries an empty name —
    the chart must call it "Unknown", like a missing value."""
    facts = (
        make_fact(**{dimension_id: ""}, paid_out_total=Decimal("10.00")),
        make_fact(**{dimension_id: "Biology"}, paid_out_total=Decimal("20.00")),
    )

    grouping = group_by(facts, dimensions.by_id(dimension_id))

    assert [(r.label, r.publications, r.is_unknown) for r in grouping.rows] == [
        ("Biology", 1, False),
        ("Unknown", 1, True),
    ]


def test__group_by_empty_input__yields_no_rows_and_a_zero_total() -> None:
    grouping = group_by((), dimensions.by_id("publisher"))

    assert grouping.rows == ()
    assert grouping.total(Measure.PUBLICATIONS) == 0
    assert grouping.total(Measure.PAID_OUT) == Decimal(0)


def test__group_by_cost_type__splits_spend_and_offers_no_publication_measure() -> None:
    facts = (
        make_fact(
            paid_out_by_cost_type={"apc": Decimal("100.00"), "vat": Decimal("19.00")},
            paid_out_total=Decimal("119.00"),
        ),
        make_fact(paid_out_by_cost_type={"apc": Decimal("50.00")}, paid_out_total=Decimal("50.00")),
    )

    grouping = group_by(facts, dimensions.by_id("cost_type"))

    assert [(r.label, r.amount) for r in grouping.rows] == [
        ("apc", Decimal("150.00")),
        ("vat", Decimal("19.00")),
    ]
    assert Measure.PUBLICATIONS not in grouping.measures
    assert grouping.total(Measure.PAID_OUT) == Decimal("169.00")


def test__group_by_cost_type__drops_cost_types_that_paid_out_nothing() -> None:
    """Without a count column a zero-money row could show nothing at all."""
    facts = (
        make_fact(
            paid_out_by_cost_type={"apc": Decimal("100.00"), "waived": Decimal("0.00")},
            paid_out_total=Decimal("100.00"),
        ),
    )

    grouping = group_by(facts, dimensions.by_id("cost_type"))

    assert [r.label for r in grouping.rows] == ["apc"]


def test__group_by_funder__counts_publications_in_full_and_carries_no_amount() -> None:
    facts = (
        make_fact(funders=("DFG", "Wellcome Trust")),
        make_fact(funders=("DFG",)),
    )

    grouping = group_by(facts, dimensions.by_id("funder"))

    assert [(r.label, r.publications, r.amount) for r in grouping.rows] == [
        ("DFG", 2, None),
        ("Wellcome Trust", 1, None),
    ]
    assert Measure.PAID_OUT not in grouping.measures
    assert grouping.total(Measure.PUBLICATIONS) is None


def test__group_by_funding_source__splits_money_and_counts_publications_non_additively() -> None:
    facts = (
        make_fact(
            funded_by={
                source("Budget A"): Decimal("60.00"),
                source("Budget B"): Decimal("20.00"),
            },
            unassigned=Decimal("20.00"),
            paid_out_total=Decimal("100.00"),
        ),
        make_fact(
            funded_by={source("Budget A"): Decimal("50.00")},
            paid_out_total=Decimal("50.00"),
        ),
    )

    grouping = group_by(facts, dimensions.by_id("funding_source"))

    assert [(r.label, r.publications, r.amount) for r in grouping.rows] == [
        ("Budget A", 2, Decimal("110.00")),
        ("Budget B", 1, Decimal("20.00")),
        ("Unassigned", 1, Decimal("20.00")),
    ]
    assert grouping.non_additive == frozenset({Measure.PUBLICATIONS})
    assert grouping.total(Measure.PUBLICATIONS) is None
    assert grouping.total(Measure.FUNDED_BY) == Decimal("150.00")


def test__group_by__folds_rows_beyond_the_top_n_into_an_other_row() -> None:
    facts = tuple(make_fact(publisher=f"p{i:02d}") for i in range(1, 14))

    grouping = group_by(facts, dimensions.by_id("publisher"), top_n=3)

    assert [(r.label, r.publications, r.is_other) for r in grouping.rows] == [
        ("p01", 1, False),
        ("p02", 1, False),
        ("p03", 1, False),
        ("Other", 10, True),
    ]
    assert grouping.total(Measure.PUBLICATIONS) == 13


def test__group_by__unbounded_top_n__keeps_every_value_without_an_other_row() -> None:
    """``top_n=None`` is the whole-of-set view (the institution treemap): no
    fold row, one row per value, in the spend-led rank."""
    facts = tuple(make_fact(publisher=f"p{i:02d}") for i in range(1, 14))

    grouping = group_by(facts, dimensions.by_id("publisher"), top_n=None)

    assert [(r.label, r.publications) for r in grouping.rows] == [
        (f"p{i:02d}", 1) for i in range(1, 14)
    ]
    assert all(not r.is_other for r in grouping.rows)
    assert grouping.total(Measure.PUBLICATIONS) == 13


def test__group_by__sums_amounts_in_the_other_row() -> None:
    facts = tuple(
        make_fact(publisher=publisher, paid_out_total=Decimal(f"{(i + 1)}.00"))
        for i, publisher in enumerate(["a", "b", "c", "d", "e"])
    )

    grouping = group_by(facts, dimensions.by_id("publisher"), top_n=2)

    assert [(r.label, r.amount, r.is_other) for r in grouping.rows] == [
        ("e", Decimal("5.00"), False),
        ("d", Decimal("4.00"), False),
        ("Other", Decimal("6.00"), True),
    ]
    assert grouping.total(Measure.PAID_OUT) == Decimal("15.00")


def test__group_by_non_additive__other_row_counts_each_request_once() -> None:
    facts = (
        make_fact(institutions=(institution("A"), institution("B"))),
        make_fact(institutions=(institution("B"), institution("C"))),
        make_fact(institutions=(institution("C"),)),
    )

    grouping = group_by(facts, dimensions.by_id("institution"), top_n=1)

    assert [(r.label, r.publications, r.is_other) for r in grouping.rows] == [
        ("B", 2, False),
        ("Other", 3, True),
    ]
    assert grouping.total(Measure.PUBLICATIONS) is None


@pytest.mark.parametrize(
    ("dimension_id", "field", "value", "expected"),
    [
        ("subject_area", "subject_area", "Computer science", ["Computer science"]),
        ("publication_type", "publication_type", "book chapter", ["book chapter"]),
        ("publication_form", "publication_form", "monograph", ["monograph"]),
        ("license", "license", "cc-zero", ["cc-zero"]),
        ("open_access_type", "open_access_type", "hybrid", ["hybrid"]),
        ("journal", "journal", "Journal of Tests", ["Journal of Tests"]),
    ],
)
def test__single_valued_dimensions__group_by_their_own_attribute(
    dimension_id: str, field: str, value: str, expected: list[str]
) -> None:
    fact = make_fact(**{"publisher": "not-this", "subject_area": "not-that", field: value})

    grouping = group_by((fact,), dimensions.by_id(dimension_id))

    assert [r.label for r in grouping.rows] == expected


def test__group_by_contract__counts_the_request_and_its_money_under_each_contract() -> None:
    dfg = ContractRef(pk=1, name="DFG 2024", year=2024)
    deal = ContractRef(pk=2, name="Deal 2026", year=2026)
    fact = make_fact(contracts=(deal, dfg), paid_out_total=Decimal("100.00"))

    grouping = group_by((fact,), dimensions.by_id("contract"))

    assert [(r.label, r.publications, r.amount) for r in grouping.rows] == [
        (dfg.label, 1, Decimal("100.00")),
        (deal.label, 1, Decimal("100.00")),
    ]
    # Each row carries its structured identity for the drill-down.
    assert {r.ref for r in grouping.rows} == {deal, dfg}
    assert grouping.non_additive == frozenset({Measure.PUBLICATIONS, Measure.PAID_OUT})


def test__registry__covers_the_twelve_dimensions_of_the_spec_table() -> None:
    assert {d.id for d in dimensions.DIMENSIONS} == {
        "institution",
        "subject_area",
        "publication_type",
        "publication_form",
        "license",
        "open_access_type",
        "journal",
        "publisher",
        "cost_type",
        "contract",
        "funder",
        "funding_source",
    }


def test__group_by__defaults_to_ten_rows_before_the_other_fold() -> None:
    facts = tuple(make_fact(publisher=f"p{i:02d}") for i in range(1, 13))

    grouping = group_by(facts, dimensions.by_id("publisher"))

    assert len(grouping.rows) == 11
    assert grouping.rows[-1].is_other

"""Direct tests for the institution-hierarchy treemap figure builder.

The figure's row walk (ids, own-publication rows, display-label transform,
tile_links) is easy to regress silently: page tests only see the rendered
mount, and every behavioral probe so far was a browser one-off. These pin
the builder's contract directly.
"""

from datetime import date
from typing import Any
from decimal import Decimal

import pytest

from coda.apps.institutions.models import Institution
from coda.apps.reporting.treemap import institution_treemap
from coda.contexts.statistics.dto import InstitutionRef, RequestFact
from tests import modelfactory


def facts_for(*institution_names: str) -> list[RequestFact]:
    """One fact per name, one publication and a fixed spend each — the
    builder only reads names through the INSTITUTION dimension."""
    return [
        RequestFact(
            request_id=index + 1,
            publication_id=index + 1,
            request_date=date(2026, 3, 15),
            title=f"Fact {index + 1}",
            subject_area=None,
            publication_type=None,
            publication_form="article",
            license="cc-by",
            open_access_type="gold",
            journal=None,
            publisher=None,
            contracts=(),
            funders=(),
            institutions=(InstitutionRef(name),),
            no_corresponding_author=False,
            paid_out_by_cost_type={},
            paid_out_total=Decimal(100 * (index + 1)),
            funded_by={},
            unassigned=Decimal(0),
            invoices_without_rate=0,
            unconvertible_invoice_ids=(),
            has_invoice=False,
        )
        for index, name in enumerate(institution_names)
    ]


def build(facts: list[RequestFact], institutions: list[Institution]) -> dict[str, Any]:
    # label_link stub: the facet URL shape is drilldown.py's business; the
    # builder contract under test is "which rows get a link", not the URL.
    figure = institution_treemap(
        facts, institutions, label_link=lambda label: f"/?institution={label}"
    )
    assert figure is not None, "treemap skipped a non-empty fact set"
    return figure


def row(figure: dict[str, Any], row_id: str) -> dict[str, Any]:
    """The full row record for one id: label, parents, values, link."""
    ids = figure["data"][0]["ids"]
    index = ids.index(row_id)
    return {
        "id": row_id,
        "label": figure["data"][0]["labels"][index],
        "parent": figure["data"][0]["parents"][index],
        "value": figure["data"][0]["values"][index],
        "link": figure["tile_links"].get(row_id),
    }


def row_by_name(figure: dict[str, Any], name: str) -> dict[str, Any]:
    """The (first) row whose original name matches — a branch and its
    own-publication row share a display label, so this returns the branch
    (emitted first). Original names ride in customdata[2]."""
    ids = figure["data"][0]["ids"]
    names = [cd[2] for cd in figure["data"][0]["customdata"]]
    return row(figure, ids[names.index(name)])


@pytest.mark.django_db
def test__treemap__ids_stay_unique_when_two_institutions_share_a_name() -> None:
    """Two same-named institutions under different parents would collide on
    a name-derived id — plotly renders zero tiles for duplicate ids. The
    own-publication row's id is suffixed; sibling names must not collide."""
    parent = modelfactory.institution()
    parent.name = "Dup Name"
    parent.save()
    child_a = modelfactory.institution()
    child_a.name = "Dup Name"
    child_a.parent = parent
    child_a.save()
    institutions = list(Institution.objects.filter(pk__in=[parent.pk, child_a.pk]))
    figure = build(facts_for("Dup Name"), institutions)

    ids = figure["data"][0]["ids"]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


@pytest.mark.django_db
def test__treemap__branch_with_own_publications_emits_both_rows() -> None:
    """A branch with own affiliations emits the branch row (value 0, link
    via the facet) and a synthetic own-publication row (value = own count,
    deliberately link-free — the facet expands a pk to its subtree)."""
    faculty = modelfactory.institution()
    faculty.name = "Test Faculty"
    faculty.save()
    institute = modelfactory.institution()
    institute.name = "Test Institute"
    institute.parent = faculty
    institute.save()
    institutions = list(Institution.objects.filter(pk__in=[faculty.pk, institute.pk]))

    figure = build(facts_for("Test Faculty", "Test Institute", "Test Faculty"), institutions)

    branch = row_by_name(figure, "Test Faculty")
    assert branch["value"] == 0  # remainder moved onto the own row
    assert branch["link"] is None  # branch tiles drill; only leaves link
    own = row(figure, f"{branch['id']}\x00own")
    assert own["parent"] == branch["id"]
    assert own["value"] == 2  # two facts affiliated with the faculty itself
    assert own["link"] is None  # facet filter would show the whole subtree


@pytest.mark.django_db
def test__treemap__display_label_strips_honorific_full_name_stays_in_hover() -> None:
    """Display labels drop 'Fakultät (für)'/'Institut für'; the hover's
    customdata keeps the original name. Container rows never wrap."""
    faculty = modelfactory.institution()
    faculty.name = "Fakultät für Testwissenschaften"
    faculty.save()
    institute = modelfactory.institution()
    institute.name = "Institut für Testkunde"
    institute.parent = faculty
    institute.save()
    institutions = list(Institution.objects.filter(pk__in=[faculty.pk, institute.pk]))

    figure = build(
        facts_for("Fakultät für Testwissenschaften", "Institut für Testkunde"), institutions
    )
    d = figure["data"][0]

    faculty_row = row_by_name(figure, "Fakultät für Testwissenschaften")
    assert faculty_row["label"] == "Testwissenschaften"  # honorific stripped, one line
    institute_id = next(
        i for i in d["ids"] if i != "root" and i != faculty_row["id"] and not i.endswith("own")
    )
    institute_index = d["ids"].index(institute_id)
    hover_name = d["customdata"][institute_index][2]
    assert hover_name == "Institut für Testkunde"  # full name for the hover

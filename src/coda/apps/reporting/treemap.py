"""The institution-hierarchy treemap (plan §9's figure vocabulary, extended).

Assembled app-side from the ORM hierarchy — the pure ``contexts/statistics``
layer has no Django — but aggregating through the same fact groupings: every
request counts in full under every one of its affiliations (ADR-0007), so a
subtree's value can exceed what its branches show; the figure carries the
non-additive note.

Roll-up (user decision): a node's area is the FULL subtree value — its own
affiliations plus all descendants' — computed exactly by summing the leaf
facts once per node; no per-child double counting is baked in beyond ADR-0007
itself. ``branchvalues="remainder"`` keeps plotly from re-summing children.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet

from coda.apps.institutions.models import Institution
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.dimensions import INSTITUTION, UNKNOWN
from coda.contexts.statistics.dto import RequestFact

#: Subtrees smaller than this are one treemap tile too many to read.
MIN_SUBTREE_PUBLICATIONS = 1

ROOT_LABEL = "All institutions"


def institution_treemap(
    facts: Sequence[RequestFact], institutions: QuerySet[Institution]
) -> dict[str, Any] | None:
    """Figure JSON for the institution hierarchy, or None when the filtered
    set has no affiliated requests. Publications is the tile size; spend is
    the colour.

    Groups ALL values (``top_n=None``): a hierarchy is a whole-of-tree view —
    no "Other" fold row, every affiliation renders at its place in the tree.
    """
    grouping = group_by(facts, INSTITUTION, top_n=None)
    by_name: dict[str, tuple[int, Decimal]] = {}
    for row in grouping.rows:
        by_name[row.label] = (row.publications, row.amount)
    # The label check stays string-based: UNKNOWN is a group-by label (the
    # "Unknown" bucket), not a row kind - kind marks the rows, the label set
    # decides whether the tree has anything to draw.
    if not by_name or set(by_name) == {UNKNOWN}:
        return None

    nodes = {node.pk: node for node in institutions.all()}
    children_of: dict[int | None, list[int]] = {}
    for pk, node in nodes.items():
        children_of.setdefault(node.parent_id, []).append(pk)

    # A request counts in full under every affiliation, so a name's value is
    # the group_by result — the tree only re-partitions those exact values.
    # One post-order walk per node sums its own value with every descendant's;
    # the "placed" set marks the names the walk emitted, so leftovers render
    # under the root.
    placed: set[str] = set()

    def add_node(pk: int, parent_label: str) -> tuple[int, Decimal]:
        node = nodes[pk]
        publications, amount = by_name.get(node.name, (0, Decimal(0)))
        for child_pk in sorted(children_of.get(pk, []), key=lambda p: nodes[p].name):
            c_pubs, c_amount = add_node(child_pk, node.name)
            publications += c_pubs
            amount += c_amount
        if publications >= MIN_SUBTREE_PUBLICATIONS:
            placed.add(node.name)
            labels.append(node.name)
            parents.append(parent_label)
            values.append(publications)
            colors.append(amount)
        return publications, amount

    labels: list[str] = [ROOT_LABEL]
    parents: list[str] = [""]
    values: list[int] = [sum(v[0] for v in by_name.values())]
    colors: list[Decimal] = [sum((v[1] for v in by_name.values()), Decimal(0))]

    for root_pk in sorted(children_of.get(None, []), key=lambda p: nodes[p].name):
        add_node(root_pk, ROOT_LABEL)

    # Names not attached to any (unarchived) institution node — e.g. the
    # "Unknown" bucket — still carry their exact value under the root.
    for name, (publications, amount) in by_name.items():
        if name not in placed:
            labels.append(name)
            parents.append(ROOT_LABEL)
            values.append(publications)
            colors.append(amount)

    figure: dict[str, Any] = {
        "data": [
            {
                "type": "treemap",
                "labels": labels,
                "parents": parents,
                "values": values,
                "branchvalues": "remainder",
                "customdata": [float(c) for c in colors],
                # Blues: high spend = dark blue. %{color} is the normalized
                # colour value, never the amount — money renders from
                # customdata.
                "marker": {
                    "colors": [float(c) for c in colors],
                    "colorscale": "OrRd",
                    "reversescale": False,
                    "colorbar": {"title": {"text": "spend €"}},
                },
                "texttemplate": "%{label}<br>%{value} pub.<br>€%{customdata:,.2f}",
                "hovertemplate": (
                    "%{label}: %{value} publications, €%{customdata:,.2f}<extra></extra>"
                ),
            }
        ],
        "layout": {
            "title": {"text": _title(), "x": 0.01, "xanchor": "left"},
            # Two-line title needs real headroom or it sits on the tiles.
            "margin": {"l": 10, "r": 10, "t": 90, "b": 10},
        },
        "config": {"responsive": True},
    }
    return figure


def _title() -> str:
    return (
        "Institution hierarchy: publications (area), spend incl. tax (colour).<br>"
        "A request counts in full under every affiliation: subtrees can overlap."
    )

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

from collections.abc import Mapping, Sequence
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
        amount = row.amount if row.amount is not None else Decimal(0)
        by_name[row.label] = (row.publications, amount)
    if not by_name or set(by_name) == {UNKNOWN}:
        return None

    nodes = {node.pk: node for node in institutions.all()}
    children_of: dict[int | None, list[int]] = {}
    for pk, node in nodes.items():
        children_of.setdefault(node.parent_id, []).append(pk)

    def subtree_pks(root_pk: int) -> list[int]:
        stack, found = [root_pk], []
        while stack:
            pk = stack.pop()
            found.append(pk)
            stack.extend(children_of.get(pk, []))
        return found

    def subtree_name_pks(root_pk: int) -> set[str]:
        return {nodes[pk].name for pk in subtree_pks(root_pk)}

    # A request counts in full under every affiliation, so a name's value is
    # the group_by result — the tree only re-partitions those exact values.
    def subtree_value(root_pk: int) -> tuple[int, Decimal]:
        names = subtree_name_pks(root_pk)
        publications = sum(by_name[n][0] for n in names if n in by_name)
        amount = sum((by_name[n][1] for n in names if n in by_name), Decimal(0))
        return publications, amount

    roots = children_of.get(None, [])
    labels: list[str] = [ROOT_LABEL]
    parents: list[str] = [""]
    values: list[int] = [sum(v[0] for v in by_name.values())]
    colors: list[Decimal] = [sum((v[1] for v in by_name.values()), Decimal(0))]

    def add_node(pk: int, parent_label: str) -> None:
        node = nodes[pk]
        publications, amount = subtree_value(pk)
        if publications < MIN_SUBTREE_PUBLICATIONS:
            return
        labels.append(node.name)
        parents.append(parent_label)
        values.append(publications)
        colors.append(amount)
        for child_pk in sorted(children_of.get(pk, []), key=lambda p: nodes[p].name):
            add_node(child_pk, node.name)

    for root_pk in sorted(roots, key=lambda p: nodes[p].name):
        add_node(root_pk, ROOT_LABEL)

    # Names not attached to any (unarchived) institution node — e.g. the
    # "Unknown" bucket — still carry their exact value under the root.
    placed = {nodes[pk].name for pk in subtree_pks_of_all(roots, children_of, nodes)}
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


def subtree_pks_of_all(
    root_pks: Sequence[int],
    children_of: Mapping[int | None, list[int]],
    nodes: Mapping[int, Institution],
) -> set[int]:
    """Every node pk under the given roots (including the roots)."""
    found: set[int] = set()
    stack = list(root_pks)
    while stack:
        pk = stack.pop()
        found.add(pk)
        stack.extend(children_of.get(pk, []))
    return found


def _title() -> str:
    return (
        "Institution hierarchy: publications (area), spend incl. tax (colour).<br>"
        "A request counts in full under every affiliation: subtrees can overlap."
    )

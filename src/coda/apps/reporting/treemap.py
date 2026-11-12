"""The institution-hierarchy treemap figure (plan §9's vocabulary, extended).

Assembled app-side from the ORM hierarchy — the pure ``contexts/statistics``
layer has no Django — but aggregating through the same fact groupings. Every
request counts in full under every one of its affiliations (ADR-0007), so
subtrees can overlap; the figure carries the non-additive note.

Plotly semantics (``branchvalues="remainder"``): a row's value is the part of
its area its children don't cover — its own publications only. Plotly sizes a
branch's outer rect as own + Σ children, so a branch still spans its subtree.
The subtree roll-up decides drawing/pruning and leaf-ness, and feeds colour
and tile text (a branch glows with its subtree's spend while its row value
holds only its own share).
"""

import re
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

from coda.apps.institutions.models import Institution
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.dimensions import INSTITUTION, UNKNOWN
from coda.contexts.statistics.dto import RequestFact

#: Subtrees smaller than this are one treemap tile too many to read.
MIN_SUBTREE_PUBLICATIONS = 1

ROOT_LABEL = "All institutions"


def institution_treemap(
    facts: Sequence[RequestFact],
    institutions: Sequence[Institution],
    label_link: Callable[[str], str | None] | None = None,
) -> dict[str, Any] | None:
    """Figure JSON for the institution hierarchy, or None when the filtered
    set has no affiliated requests. Publications is the tile size; spend is
    the colour. Groups all values (no "Other" fold): a hierarchy is a
    whole-of-tree view."""
    grouping = group_by(facts, INSTITUTION, top_n=None)
    by_name: dict[str, tuple[int, Decimal]] = {}
    for row in grouping.rows:
        by_name[row.label] = (row.publications, row.amount)
    # UNKNOWN is a group-by label, not a row kind: the label set decides
    # whether there is anything to draw.
    if not by_name or set(by_name) == {UNKNOWN}:
        return None

    nodes = {node.pk: node for node in institutions}
    children_of: dict[int | None, list[int]] = {}
    for pk, node in nodes.items():
        children_of.setdefault(node.parent_id, []).append(pk)

    # Sums and drawn decisions in one post-order pass; rows appended in a
    # second, pre-order pass — plotly resolves parent-child area relations in
    # row order, so a child row preceding its parent packs the tree into a
    # corner of the root tile.
    placed: set[int] = set()
    subtree_sums: dict[str, tuple[int, Decimal]] = {}
    subtree_leaf: dict[str, bool] = {}

    def subtree_stats(pk: int) -> tuple[int, Decimal, bool]:
        node = nodes[pk]
        publications, amount = by_name.get(node.name, (0, Decimal(0)))
        any_drawn_child = False
        for child_pk in sorted(children_of.get(pk, []), key=lambda p: nodes[p].name):
            c_pubs, c_amount, c_drawn = subtree_stats(child_pk)
            publications += c_pubs
            amount += c_amount
            any_drawn_child = any_drawn_child or c_drawn
        drawn = publications >= MIN_SUBTREE_PUBLICATIONS
        if drawn:
            placed.add(pk)
            subtree_sums[f"i{pk}"] = (publications, amount)
            subtree_leaf[f"i{pk}"] = not any_drawn_child
        return publications, amount, drawn

    def add_node(pk: int, parent_id: str) -> None:
        node = nodes[pk]
        if pk not in placed:
            return
        own_publications, own_amount = by_name.get(node.name, (0, Decimal(0)))
        row_id = f"i{pk}"
        _, amount = subtree_sums[row_id]
        # A branch with drawn children hangs a synthetic own-publication row
        # below, so its remainder becomes a labeled tile instead of unlabeled
        # parent area; the branch row itself then carries 0. The two rows
        # share a display label, so identity moves to ids (unique per row);
        # parents reference ids. Ids are pk-based — two institutions can
        # share a name, and plotly renders zero tiles for duplicate ids.
        has_own_leaf = own_publications > 0 and subtree_leaf[row_id] is False
        labels.append(node.name)
        ids.append(row_id)
        id_names[row_id] = node.name
        parents.append(parent_id)
        values.append(0 if has_own_leaf else own_publications)
        colors.append(amount)
        subtree_publications.append(subtree_sums[row_id][0])
        for child_pk in sorted(children_of.get(pk, []), key=lambda p: nodes[p].name):
            add_node(child_pk, row_id)
        if has_own_leaf:
            # Not subtree_leaf: the institution facet expands every selected
            # pk to its whole subtree (InstitutionCriteria), so a link here
            # would show more than the tile's area. Tracked in
            # synthetic_labels — the row's id, not its display label.
            own_id = f"i{pk}\x00own"
            ids.append(own_id)
            id_names[own_id] = node.name
            synthetic_labels.add(own_id)
            labels.append(node.name)
            parents.append(f"i{pk}")
            values.append(own_publications)
            colors.append(own_amount)
            subtree_publications.append(own_publications)

    labels: list[str] = [ROOT_LABEL]
    ids: list[str] = ["root"]
    id_names: dict[str, str] = {"root": ROOT_LABEL}
    parents: list[str] = [""]
    synthetic_labels: set[str] = set()
    # Root value 0: it is a pure container. A non-zero root value reserves a
    # visible tile of its own and packs the tree into its corner.
    values: list[int] = [0]
    colors: list[Decimal] = [sum((v[1] for v in by_name.values()), Decimal(0))]
    subtree_publications: list[int] = [sum(v[0] for v in by_name.values())]

    for root_pk in sorted(children_of.get(None, []), key=lambda p: nodes[p].name):
        subtree_stats(root_pk)
        add_node(root_pk, "root")

    # Names outside any (unarchived) node — e.g. the "Unknown" bucket, or a
    # name whose institution is archived — carry their exact value under the
    # root.
    drawn_names = {nodes[pk].name for pk in placed}
    for name, (publications, amount) in by_name.items():
        if name not in drawn_names:
            labels.append(name)
            ids.append(f"u{name}")
            id_names[f"u{name}"] = name
            parents.append("root")
            values.append(publications)
            colors.append(amount)
            subtree_publications.append(publications)
            subtree_leaf[f"u{name}"] = True

    # Display labels drop the "Fakultät (für)" / "Institut für" honorifics —
    # a one-line container label cannot fit a narrow tile otherwise, and the
    # leaf labels gain room to wrap. Container rows stay on one line; leaves
    # wrap at word boundaries. The full name stays in customdata for the
    # hover. Rows are identified by ids (unique per row — a branch and its
    # own-publication row share a display label); labels carry the wrapped
    # display string, keyed to ids.
    leaf_ids = {row_id for row_id, leaf in subtree_leaf.items() if leaf} - synthetic_labels
    id_wrap_map = {
        row_id: (
            _wrap_label(re.sub(r"^(?:Fakultät|Institut) (?:für )?", "", label))
            if row_id in leaf_ids
            else re.sub(r"^(?:Fakultät|Institut) (?:für )?", "", label)
        )
        for row_id, label in zip(ids, labels)
    }
    labels = [id_wrap_map[row_id] for row_id in ids]
    # parents stay ids verbatim (the walk emits ids): plotly resolves them
    # against the ids array.
    # id -> original (unwrapped, unduplicated) name for the facet lookup;
    # built at emission time (id_names), so no string surgery on ids.
    tile_link_labels = dict(id_names)

    # Font sizes: plotly's own fit (default textfont sizing) owns the label
    # size — the server-side tiers only fought it (and the client pass).

    # Leaf tiles link like the drilldown filters (§2 #7); branch tiles keep
    # plotly's own drilldown (the subtree filter doubles as the walk
    # position — the two roles must not diverge). Keyed by id, not label:
    # a branch and its own-publication row share a display label, and the
    # id is stable across drilldown. Links resolve through the original
    # name; the facet's label→pk table knows the unwrapped forms.
    tile_links: dict[str, str | None] | None = None
    if label_link is not None:
        tile_links = {
            row_id: (
                label_link(tile_link_labels[row_id])
                if subtree_leaf.get(row_id, False) and row_id not in synthetic_labels
                else None
            )
            for row_id in ids
        }

    figure: dict[str, Any] = {
        "tile_links": tile_links,
        "data": [
            {
                "type": "treemap",
                "ids": ids,
                "labels": labels,
                "parents": parents,
                "values": values,
                "branchvalues": "remainder",
                # customdata: [subtree spend, subtree publications, original
                # name] — templates show subtree figures (not the row's
                # remainder value) and the unwrapped name.
                "customdata": [
                    [float(c), p, tile_link_labels[row_id]]
                    for c, p, row_id in zip(colors, subtree_publications, ids)
                ],
                "marker": {
                    "colors": [float(c) for c in colors],
                    "colorscale": "OrRd",
                    "reversescale": False,
                    # Anchored on the drawn tiles: the root's whole-period
                    # colour would otherwise pin the scale's top end above
                    # every tile whenever unattached spend exists.
                    "cmin": 0,
                    "cmax": max((float(c) for c in colors[1:]), default=0.0) or 1.0,
                    "colorbar": {"title": {"text": "spend €"}},
                },
                "texttemplate": "%{label}<br>%{customdata[1]} pub.<br>€%{customdata[0]:,.2f}",
                "hovertemplate": (
                    "%{customdata[2]}: %{customdata[1]} publications,"
                    " €%{customdata[0]:,.2f}<extra></extra>"
                ),
            }
        ],
        "layout": {
            "title": {"text": _title(), "x": 0.01, "xanchor": "left"},
            "margin": {"l": 10, "r": 10, "t": 90, "b": 10},
        },
        "config": {"responsive": True},
    }
    return figure


def _wrap_label(label: str, width: int = 18) -> str:
    """Break a name into lines of at most `width` characters, splitting on
    spaces and hyphens. Display only: line-final spaces are dropped (hyphens
    stay), so a wrapped label is not an identity — match facet names against
    the original, never the wrapped form."""
    if len(label) <= width:
        return label
    lines: list[str] = []
    current = ""
    for part in re.split(r"(?<=[ -])", label):
        if current and len(current) + len(part) > width:
            lines.append(current)
            current = part
        else:
            current += part
    if current:
        lines.append(current)
    return "<br>".join(line.rstrip() for line in lines)


def _title() -> str:
    return (
        "Institution hierarchy: publications (area), spend incl. tax (colour).<br>"
        "A request counts in full under every affiliation: subtrees can overlap."
    )

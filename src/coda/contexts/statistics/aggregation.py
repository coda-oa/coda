"""Grouping facts by dimension (plan §4, §7; ADR-0007).

Pure: takes RequestFact values, returns Grouping values. Repeated dimensions count a
fact in full under every one of its values; the non-additive flags on the result tell
the page it must not print a total for such rows. One grouping per dimension carries
*all* supported measures per row, so a facet renders one reconciling table and its
charts share exactly its row set.
"""

from collections.abc import Sequence
from decimal import Decimal

from coda.contexts.statistics.dimensions import OTHER, UNASSIGNED, UNKNOWN, ZERO, Dimension
from coda.contexts.statistics.dto import Grouping, GroupRow, Measure, RequestFact

DEFAULT_TOP_N = 10


def group_by(
    facts: Sequence[RequestFact],
    dimension: Dimension,
    *,
    top_n: int | None = DEFAULT_TOP_N,
) -> Grouping:
    spend = dimension.money
    counts_values = Measure.PUBLICATIONS in dimension.measures()

    counts: dict[str, int] = {}
    amounts: dict[str, Decimal] = {}
    sources: dict[str, set[int]] = {}
    refs: dict[str, object] = {}
    for fact in facts:
        contributions = dimension.contributions(fact)
        for label in dict.fromkeys(contribution.label for contribution in contributions):
            counts[label] = counts.get(label, 0) + 1
            sources.setdefault(label, set()).add(fact.request_id)
        for contribution in contributions:
            amounts[contribution.label] = (
                amounts.get(contribution.label, ZERO) + contribution.amount
            )
            if contribution.ref is not None:
                refs[contribution.label] = contribution.ref

    def row(label: str) -> GroupRow:
        return GroupRow(
            label=label,
            publications=counts[label],
            amount=amounts[label] if spend is not None else None,
            is_unknown=label == UNKNOWN,
            is_unassigned=label == UNASSIGNED,
            ref=refs.get(label),
        )

    def rank(label: str) -> tuple[Decimal, int, str]:
        # Money leads the ranking — this is a funding report, and paid-out
        # entities must never be pushed off the visible top by ones that were
        # funded but paid nothing (no invoice, unconvertible amounts per
        # ADR-0003); those rank by count below them. A dimension without a
        # count measure (cost type) ranks purely by money.
        amount = -amounts.get(label, ZERO) if spend is not None else ZERO
        publications = -counts[label] if counts_values else 0
        return (amount, publications, label)

    # Without a count column, a zero-money row could show nothing at all —
    # it is noise (cf. UNASSIGNED, contributed only when non-zero).
    labels = sorted(
        (label for label in counts if counts_values or amounts.get(label, ZERO) != ZERO),
        key=rank,
    )
    if top_n is None:
        # Unbounded: every value keeps its own row — a whole-of-set view
        # (the institution treemap) must not fold anything into "Other".
        rows = [row(label) for label in labels]
        return Grouping(
            dimension_id=dimension.id,
            dimension_label=dimension.label,
            measures=dimension.measures(),
            non_additive=frozenset(
                measure for measure in dimension.measures() if not dimension.is_additive(measure)
            ),
            rows=tuple(rows),
        )

    rows = [row(label) for label in labels[:top_n]]
    folded = labels[top_n:]
    if folded:
        rows.append(
            GroupRow(
                label=OTHER,
                publications=len({rid for label in folded for rid in sources[label]}),
                amount=(
                    sum((amounts[label] for label in folded), ZERO) if spend is not None else None
                ),
                is_other=True,
            )
        )
    return Grouping(
        dimension_id=dimension.id,
        dimension_label=dimension.label,
        measures=dimension.measures(),
        non_additive=frozenset(
            measure for measure in dimension.measures() if not dimension.is_additive(measure)
        ),
        rows=tuple(rows),
    )

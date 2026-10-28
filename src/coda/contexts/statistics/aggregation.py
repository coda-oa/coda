"""Grouping facts by dimension (plan §4, §7; ADR-0007).

Pure: takes RequestFact values, returns Grouping values. Repeated dimensions count a
fact in full under every one of its values; the non-additive flags on the result tell
the page it must not print a total for such rows. One grouping per dimension carries
*all* supported measures per row, so a facet renders one reconciling table and its
charts share exactly its row set.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from coda.contexts.statistics.dimensions import OTHER, UNASSIGNED, UNKNOWN, ZERO, Dimension
from coda.contexts.statistics.dto import Grouping, GroupRow, Measure, RequestFact, RowKind

DEFAULT_TOP_N = 10


@dataclass
class _LabelAcc:
    """Per-label accumulator. Money sums per contribution; publications are
    the cardinality of distinct request ids — a repeated dimension contributes
    a fact in full under every value (ADR-0007), but the publication counts
    once per value. That cardinality rule is sound because the fact grain is
    one row per funding request (``search()`` fetches ``.distinct()``).
    ``ref``: the value's structured identity; when several contributions share
    a label, the last one carrying a ref wins (same as before)."""

    amount: Decimal = ZERO
    request_ids: set[int] = field(default_factory=set)
    ref: object | None = None

    def add(self, fact: RequestFact, amount: Decimal, ref: object | None) -> None:
        self.amount += amount
        self.request_ids.add(fact.request_id)
        if ref is not None:
            self.ref = ref


def group_by(
    facts: Sequence[RequestFact],
    dimension: Dimension,
    *,
    top_n: int | None = DEFAULT_TOP_N,
) -> Grouping:
    spend = dimension.money
    counts_values = Measure.PUBLICATIONS in dimension.measures()

    accs: dict[str, _LabelAcc] = {}
    for fact in facts:
        for contribution in dimension.contributions(fact):
            acc = accs.setdefault(contribution.label, _LabelAcc())
            acc.add(fact, contribution.amount, contribution.ref)

    def row(label: str) -> GroupRow:
        acc = accs[label]
        kind = _row_kind(label)
        return GroupRow(
            label=label,
            publications=len(acc.request_ids),
            amount=acc.amount,
            kind=kind,
            ref=acc.ref,
        )

    def _row_kind(label: str) -> RowKind:
        if label == UNKNOWN:
            return RowKind.UNKNOWN
        if label == UNASSIGNED:
            return RowKind.UNASSIGNED
        return RowKind.VALUE

    def rank(label: str) -> tuple[Decimal, int, str]:
        # Money leads the ranking — this is a funding report, and paid-out
        # entities must never be pushed off the visible top by ones that were
        # funded but paid nothing (no invoice, unconvertible amounts per
        # ADR-0003); those rank by count below them. A dimension without a
        # count measure (cost type) ranks purely by money.
        amount = -accs[label].amount if spend is not None else ZERO
        publications = -len(accs[label].request_ids) if counts_values else 0
        return (amount, publications, label)

    # Without a count column, a zero-money row could show nothing at all —
    # it is noise (cf. UNASSIGNED, contributed only when non-zero).
    labels = sorted(
        (label for label in accs if counts_values or accs[label].amount != ZERO),
        key=rank,
    )
    # Unbounded (top_n=None): every value keeps its own row — a whole-of-set
    # view (the institution treemap) must not fold anything into "Other".
    # (Slicing with None would misbehave: labels[None:] is labels[0:].)
    visible = labels[:top_n]
    folded = labels[top_n:] if top_n is not None else []
    rows = [row(label) for label in visible]
    if folded:
        fold_ids: set[int] = set()
        fold_amount = ZERO
        for label in folded:
            fold_ids |= accs[label].request_ids
            fold_amount += accs[label].amount
        rows.append(
            GroupRow(
                label=OTHER,
                publications=len(fold_ids),
                amount=fold_amount,
                kind=RowKind.OTHER,
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

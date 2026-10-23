# Paid-out and funded-by are separate measures

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

Spend is reported in two notions that are never mixed and never added together:

- **Paid out** — the gross totals of a request's invoice positions: what the institution paid to
  publishers, journals and other creditors. Used for the publication-facing dimensions (publisher,
  journal, subject area, license, open access type, cost type, contract, publication).
- **Funded by** — the gross amounts of the positions' funding assignments: which internal funding
  source actually paid. Used for the funding-source dimension, whose institution-kind values are the
  cost-splitting institutions. This is a different dimension from the one in ADR-0006, which
  attributes paid-out money to the institution a corresponding author is affiliated with.

A publisher chart must answer what was paid; a funding-source chart must answer who paid it. One
number cannot serve both, and a single chart mixing them double counts the money that was paid out
of one budget and to one publisher at the same time.

## Consequences

A position need not be fully assigned to funding sources, so the unassigned remainder appears as its
own slice on funded-by charts, which therefore still reconcile to the request total. Where another
institution paid part of an invoice, the paid-out total legitimately exceeds the sum of the
institution's own funded-by figures; that difference is information, not an inconsistency.

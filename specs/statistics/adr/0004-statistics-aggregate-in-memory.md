# Statistics aggregate in memory from the existing fetch

Status: proposed

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

The page recomputes on every filter change. It builds one typed fact set from the existing
funding-request/invoice prefetch and aggregates it in memory in plain Python, rather than adding a SQL
`GROUP BY` layer. The fetch already runs in a constant number of queries (the export prefetch is
test-pinned, and the openCost pipeline documents ~50-80 queries regardless of dataset size), and
periods are small: a real openCost report in this repository holds ~700 publications, and the
repository's "realistic" performance dataset is 1,000 publications.

The money semantics are the whole difficulty of this feature: gross versus net, assignment versus
position totals, invoice-level currency. One in-memory implementation keeps them in one place. A SQL
aggregation path would be a second implementation of the same rules, on multi-join queries where
fan-out silently double-counts sums — the exact bug the existing pipeline avoids by flattening in
Python.

## Consequences

A period's whole graph is held in memory per in-flight request, and memory scales with the period,
not with the page. If a period ever covers an order of magnitude more rows than today (~10⁴
publications), this is the first decision to revisit; the aggregation seam is the interface to
change, not the fetch.

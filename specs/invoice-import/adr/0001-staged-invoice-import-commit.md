# Defer invoice import entity writes until invoices pass validation

Invoice imports of roughly 2,000–5,000 invoices create creditors, funding sources, and contracts while building lookups, before position parsing and the `UnassignedCosts`/`InvalidSplitAmount` invariants can reject an invoice. Rejected invoices therefore leave orphaned rows. We chose a staged plan/commit boundary: resolve existing entities read-only, stage missing domain entities in memory, parse positions and validate every invoice, then in one service-level `transaction.atomic()` commit only entities referenced by surviving invoices in the order creditors → funding sources → contracts → invoices → payment updates. Per-invoice savepoints were rejected because they cost roughly 12–16 round trips per invoice (60k–80k queries at 5k) and discard the existing bulk-write path; post-hoc pruning was rejected because it risks pre-existing data; DTO-level cost checks were rejected because they duplicate tax and implicit-assignment arithmetic.

## Considered Options

- Per-invoice `transaction.atomic()` savepoints: no duplicate domain math, but per-invoice lookups and persistence make 2k–5k imports an order of magnitude slower.
- Prune unreferenced entities after import: risks deleting rows belonging to pre-existing invoices and requires reference bookkeeping.
- Recompute assigned costs from import DTOs before lookups: duplicates domain arithmetic and can diverge from `Position`.
- Chunked staged commit: rejected because partial commits expose partial imports and weaken all-or-nothing failure behavior.
- Background worker for large imports: not selected; imports run synchronously inside one web request/transaction, accepting request duration and timeout risk at 2k–5k rather than adding worker infrastructure.
- Shared unit-of-work across invoice, funding-request, and DOI importers: rejected; their entity sets and failure semantics differ, so only concrete helpers (contract lookup) are shared and each importer owns its commit.
- Staged plan/commit: chosen.

## Consequences

- The paid/unassigned invariant moves to `Invoice.ensure_all_costs_assigned(status, positions)` so planning can validate before creditor IDs exist; final invoices are constructed after entity commit.
- `ImportLookups` carries a `FundingSourceStaging` with one funding-source map keyed by `(kind, name)` plus staged `Contract`s; commit backfills IDs onto the same instances embedded in positions. Contract IDs are matched by name because `contract_repository.create_many` returns freshly mapped copies; funding-source IDs are assigned back in input order because `create_many` fills results positionally.
- Contract period aggregation and existing-contract lookup are shared as read-only `contract_periods`/`find_contracts` helpers; invoice import owns deferred creation and ID copy-back.
- Funding sources resolve by `(kind, name)`: a legacy `funding_source` occupies `("budget", name)`, and each `funding_assignments` entry resolves by its declared `type`. A budget and an institution sharing a name therefore resolve independently; budgets are created if missing, institutions must already exist. A position that sets both `funding_source` and `funding_assignments` is rejected during DTO validation instead of one side being silently ignored.
- Creditor batch creation moves behind the invoices app repository instead of direct ORM calls from the contexts layer.
- Import behavior tests stay black-box at `import_invoices`; no query-count guard was added for the 2k–5k requirement, so the constant-query property of the commit phase is protected only by review.

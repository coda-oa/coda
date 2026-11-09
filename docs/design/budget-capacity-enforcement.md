# Budget Capacity Enforcement — closing the over-assignment hole

This spec locks the enforcement design for budget capacity on the invoice path, so that distributing an invoice position's amount over multiple funding assignments can no longer push a budget past its limit. It is the destination artifact of the wayfinder map [Budget Capacity Enforcement — the over-assignment bug](../../.wayfinder/budget-capacity-enforcement/map.md); every section cites the ticket whose resolution it compiles. Nothing here re-opens the budget-system design itself — see [docs/design/budget-system.md](budget-system.md) and [ADR 0001](../adr/0001-budget-cost-basis.md) for the settled model.

## 1. The bug being fixed

`ensure_assignment_capacity` (`src/coda/contexts/finance/services/budget_service.py:68-93`) checks each funding assignment's delta in isolation against DB bookings that do not yet include the invoice being saved. Two failures:

1. **No aggregation across assignments**: two 60-assignments against a limit of 100 both pass individually ("0 + 60 ≤ 100", twice); the invoice then commits 120.
2. **Wrong edit-delta arithmetic**: the invoice-wide persisted total (`_persisted_assignment_totals`, `budget_service.py:96-125`) is subtracted from *each* single assignment's amount. Editing a persisted 60+60 into 100+100 yields deltas of −20 each, no check runs, and the budget's commitment rises 120 → 200 unchecked.

The pure rule (`check_capacity`, `src/coda/domain/finance/budget_capacity.py:36-50`) and the read model (`budget_balances`, `src/coda/apps/invoices/budget_query.py:104-185`) are aggregate-correct; the orchestration loop is the sole defect.

## 2. The invariant ([Invariant and delta arithmetic](../../.wayfinder/budget-capacity-enforcement/tickets/01-invariant-and-delta-arithmetic.md))

For every (budget, currency):

> committed(bookings, excluding this invoice) + Σ(new assignments to that budget) ≤ limit

- The check runs **once per budget**, never once per assignment.
- `limit` and the `allow_over`/`allowance` semantics are the uniform capacity rule already decided in the budget-system map ([What happens when a budget goes over?](../../.wayfinder/tickets/03-over-budget.md)): amount + allowance when allowed over, the amount itself otherwise.
- **Edit-delta arithmetic**: per (budget, currency), delta = Σ(new gross assignments on this invoice) − the invoice's own persisted gross total. Only positive deltas are checked; a delta ≤ 0 is not a new commitment. Gross means the same rounded gross expression the read model uses, so a net snapshot is never compared against a gross commitment.
- The guard runs on the **complete new invoice before any persistence** — and, per §6, inside the same transaction that writes the booking.

## 3. The shared domain primitive

The review-split path already works; it becomes the template, not just a precedent:

- **Delta computation moves to the domain and generalizes.** `FundingSplits.positive_delta` / `DecidedFunding.delta_over` (`src/coda/domain/fundingrequest/review.py:91-116`) is generalized to key by **(source, currency)** so both review splits and invoice assignments feed the same "sum → subtract own persisted totals → positive deltas" function. Review's single-currency world (splits pinned to the decided currency) is the special case; its behavior is unchanged.
- **One pure verdict function.** A new `check_commitment_capacity` in `src/coda/domain/finance/budget_capacity.py`: bookings per budget + positive deltas per budget → `CapacityVerdict` per budget. Pure, unit-testable without DB.
- **The service raises.** The domain returns verdicts; `budget_service` translates a rejected verdict into `BudgetCapacityExceededError` (`budget_service.py:34-36`), unchanged type and message shape (budget name + over-amount).
- **The review path migrates** onto the shared primitive — zero behavior change; two callers prove the abstraction.

## 4. Covered write paths ([Inventory of write paths touching budget commitments](../../.wayfinder/budget-capacity-enforcement/tickets/02-write-paths-inventory.md))

All writes funnel through three choke points; the guard placement follows the callers:

| Path | Writes | Enforcement |
|---|---|---|
| Invoice create / update / inspect pay+reset → `invoice_service.save` | Assignment rows (mapper `bulk_create`), COMMITMENT ledger rows | Summed-delta guard (§2) |
| Review decision → `update_review` → `save_review` | Split rows, COMMITMENT ledger rows | Already sums deltas; migrates onto the shared primitive (§3) |
| Invoice import → `repository.create_many` | Assignment rows + ledger rows for the whole batch | Batch guard (§5) |
| Transfers / `add_funds` | Transfer + ledger rows | Already correct (outflow checked, incoming exempt) |

- **`add_test_invoices` management command** routes around `invoice_service.save` (`apps/invoices/repository.py:51`) — guard and ledger booking both skipped. **Decided (2026-11-09, test-plan grilling)**: the command is routed through the guarded save path, so its invoices pass the guard and book ledger rows like any other data.
- **`update_extra_information`** calls `save_review` unguarded, but carries the splits through unchanged (zero delta). The spec requires an assertion or comment pinning that invariant so a future change can't silently turn it into a commitment path.
- **No admin writes, no fixtures, no other migrations** touch these models (verified in the inventory); data migration `0020` is one-time history.
- Read model fact that shapes all of the above: `budget_balances` derives reserved/spent from assignment and split rows, **not** ledger rows — any path writing assignment rows changes capacity reckoning whether or not a guard runs.

## 5. Import ([Import exemption for the capacity check](../../.wayfinder/budget-capacity-enforcement/tickets/03-import-exemption.md))

- Import **enforces** capacity: the batch's summed per-(budget, currency) delta is checked against every budget involved.
- **Exemptions, precisely scoped**:
  - Placeholder budgets the import run itself auto-created (`_entity_creation.py:53-56`) are exempt — detected by creation, not by zero amount; a pre-existing budget (even deliberately 0-amount) always gets the real check.
  - Already-paid imported invoices can never be *blocked* (they record external reality), but their commitments **count toward the batch's summed delta** for the unpaid rows.
  - No extra currency exemption: a conversion rate present in the import data is a rate; converted amounts join the batch delta ([Foreign-currency commitments](../../.wayfinder/budget-capacity-enforcement/tickets/04-foreign-currency-invisibility.md) §composition).
- **On breach the whole batch is rejected**: `repository.create_many` is already `@transaction.atomic` (`apps/invoices/repository.py:62`); the error names the budget and the over-amount. No skip-offending or warn-and-proceed mode. Per-invoice checking is explicitly rejected — two invoices in one batch to the same budget must not each pass in isolation.

## 6. Concurrency ([Concurrent saves racing the capacity check](../../.wayfinder/budget-capacity-enforcement/tickets/06-concurrency.md))

- **Check and book share one transaction.** For every guarded path the spec mandates a single atomic block: lock budget rows → compute deltas → verdict → mapper write → commit. A guard outside the transaction whose write it protects releases the lock before the booking lands; the race remains.
- **Budget-row locks**: the check-and-book window locks the involved budget rows (`select_for_update`), mirroring the transfer path's existing discipline (`budget_service.py:150-152`).
- **All guarded paths**: invoice saves, review decisions, import batch.
- **Deterministic lock ordering**: budgets are locked in sorted-id order; overlapping saves in different orders cannot deadlock.
- A DB constraint backstop was rejected: the invariant spans assignments + splits + transfers and is derived by the read model — a plain constraint cannot express it, and a materialized balance column is a larger redesign than this effort.

## 7. Currency semantics ([Foreign-currency commitments invisible to the capacity check](../../.wayfinder/budget-capacity-enforcement/tickets/04-foreign-currency-invisibility.md), [When the rate-time check refuses the real rate](../../.wayfinder/budget-capacity-enforcement/tickets/08-rate-refusal-deadlock.md))

- **Commitment time**: rate-pending commitments (no conversion rate) stay invisible to the check — the prior map's accepted risk stands. Proxy rates rejected: rates genuinely arrive later.
- **Rate-time branch in the invoice-save guard**: an assignment whose position currency has a conversion rate to the budget's currency contributes its **converted** amount to the summed per-budget delta; without a rate it is skipped. Rates are entered on the invoice create/edit forms (`views/create.py:29-40`, `views/update.py:86-115`) and persist via `invoice_service.save`, so no separate enforcement surface exists. Applies to manual entry regardless of paid status; the import paid exemption stays import-specific.
- **A rate is a measurement, never blocked**: adding a rate to an already-saved invoice always proceeds (delta = 0); the budget's derived-exceeded status surfaces any overrun. Blocking would block recording real spend and invite false rates. When a recorded rate pushes a budget over, the flow shows a **non-blocking warning** ("this rate pushes budget X over by N") through the verdict seam (§8).
- **Fresh-save refusal** (assignments + rate together over capacity): plain error, budget + over-amount. The rate-less escape (dropping the rate and saving rate-pending) is *not advertised*; it remains possible and self-resolving — recording the rate later always proceeds and surfaces the overrun as exceeded.
- **The verdict seam exposes rate-pending figures** as part of its contract (committed and rate-pending exposure per budget/currency). Consumers decide whether to render them: the invoice wizard deliberately shows converted amounts only (§8); the budget page remains the pending-exposure surfacing point via the read model's `pending` bucket. The capability must not be stripped as dead weight.

## 8. Error surfacing ([Where does the user see the capacity rejection?](../../.wayfinder/budget-capacity-enforcement/tickets/05-rejection-surfacing.md))

- **Live feedback in the distribution step**: the wizard's HTMX endpoints show per-budget "available after this distribution", computed from the same domain deltas + service verdicts as the review screen's live feedback (`views/review.py:295-330` is the pattern). In-session, not-yet-persisted assignments are included; rows go red when negative. Informational only — the save-time guard enforces.
- **Save-time errors keep the flash + re-render pattern**, uniform across create/update/inspect (`views/create.py:44-45`, `views/update.py:64-65` already do this), message naming the budget and the over-amount. The spec closes the one gap: `inspect.pay_invoice` calls `invoice_service.save` without catching `DomainError` (`views/inspect.py:225-234`) — currently benign because pay/reset deltas are zero, but an uncaught-500 path.
- **Rate-overrun warning on the success path** (from §7 and [When the rate-time check refuses the real rate](../../.wayfinder/budget-capacity-enforcement/tickets/08-rate-refusal-deadlock.md) §3): when a recorded rate pushes a budget over, the flow proceeds but flashes a non-blocking warning — "this rate pushes budget X over by N" — through the same verdict seam as the errors above. It is a success-path message, never a block; the budget's derived-exceeded status carries the standing record.

## 9. Test gaps the implementation must close

- **The reported bug's scenario is untested**: no existing test distributes one invoice's positions over multiple assignments to the same budget (`tests/invoices/test_budget_service.py` uses single-assignment fixtures). Required: multi-assignment-same-budget rejection, and the edit case (persisted 60+60 → 100+100 must be caught).
- Import batch tests: two invoices in one batch to the same budget (batch-summed, not per-invoice); placeholder-budget exemption; paid-import counting.
- Shared-primitive tests: pure `check_commitment_capacity` (domain, no DB) plus the review path's unchanged behavior after migration.
- Concurrency: **decided (2026-11-09, test-plan grilling)** — the lock discipline and same-transaction check-and-book are covered by code review against the transfer suite's precedent (`budget_service.py:150-152`), not by tests: a transaction-introspection assertion would be implementation-coupled (breaks on refactor without behavior change). The plan's "deliberately not tested" list records this.

## 10. Out of scope

- Implementation itself (models, code, migrations) — built after this spec, outside the map.
- Retroactive audit/cleanup of already over-assigned budgets — prevent new overspends only.
- The budget-system design (attributes, states, transfers, UI) — settled by the prior map.
- Monitoring/reporting use cases — separate future effort (prior map's out-of-scope note stands).

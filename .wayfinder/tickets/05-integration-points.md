---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["02-budget-states"]
---

# Where do budget state changes hook into existing workflows?

## Question

Pin down the integration points — which existing events produce budget bookings, and where the accounting layer sits:

- **Funding request decided** (review result → approved with `decided_funding`): **settled** by [What do budget states mean and when do they apply?](02-budget-states.md) — approval records the intended funding source(s) + split on the review (new explicit FR→funding-source link) and creates the reservation; the invoice arrives later and its assigned amount replaces the reserved amount until paid.
- **Invoice paid** (`Invoice.pay()`, `src/coda/domain/finance/invoice.py:118-121`): **settled** — the invoice's reserved portion converts to spent, the FR reservation is released; unassigned costs never touch a budget.
- **Funding assignment edited/removed**, invoice reset (`reset_payment`), review revised/waived/rejected: **settled** by derivation — reserved/spent recompute from rows, so no reversal/amendment logic exists; only persisted transfers would need explicit handling.
- **Architecture placement**: view → query service → service (`contexts/`) → repository (`apps/`) → DB is the house rule; where do budget calculations live — derived in query services, or persisted bookings? (Also feeds the map's fog on persistence shape.) Enforcement points are **settled** by [What happens when a budget goes over?](03-over-budget.md): the capacity rule is wired at FR approval and funding assignment, never at payment.
- Currency: **settled** — bookings stay in original currency; rate-pending ones sit in a pending-conversion bucket until the bank rate is entered (see 02-budget-states resolution §7).

Blocked by [02-budget-states](02-budget-states.md).

## Resolution

Decided 2026-11-04 (grilling, 1 round; all behavioral questions were pre-settled by 02/03):

1. **Balance overview — SQL read model**: a query service in `apps/invoices` (sibling of `invoice_query`/`fundingrequest_query`) aggregates reserved/spent/credited/debit per budget in SQL and maps to `Money`/DTOs. No Python-side row loops.
2. **Capacity check — pure domain function**: at commitment time the check runs over one budget's bookings (small row set) as a Django-free domain function, so the rule stays unit-testable and the domain stays pure.
3. **Enforcement — contexts service**: a `contexts/finance` service owns the capacity rule and is called by the funding-request review flow and the invoice assignment flow; views never check budgets directly (never-bypass-the-service-layer rule).
4. **FR→funding-source split capture**: on the existing review screen — which is already separate from the create/update wizards — alongside the decided funding amount.
5. **Transfers — `apps/invoices`**: the persisted transfer entries live next to `FundingSource` (new model + migrations); transfer services in `contexts/finance`. No new Django app.
6. **No event listeners, no reversal logic**: derivation means nothing subscribes to invoice payment or review changes; only transfer creation is a write path beyond existing flows. The booking ledger (see [What must the budget model record for future monitoring?](07-monitoring-data-requirements.md) §1) is written by the same service calls, not by listeners.

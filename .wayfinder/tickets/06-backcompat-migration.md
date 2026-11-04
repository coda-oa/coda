---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["01-budget-attributes", "02-budget-states"]
---

# How do existing budgets and assignments map onto the new model?

## Question

Back-compat and migration, in scope per the map Notes:

- Existing budget-type funding sources have no amount/period and are already referenced by `FundingAssignment` rows and UI filters (`src/coda/apps/invoices/views/fundingsources.py:55`). After the new model lands: do existing budgets become amount-less/open-ended budgets, start empty with history untracked, or get retrofitted amounts?
- Historical funding assignments and paid/unpaid invoices: are they booked retroactively into the new state model (spent/reserved computed from existing rows), or does accounting start at cutover?
- The create/edit views currently take `fields = ["name"]` only (`src/coda/apps/invoices/views/fundingsources.py:22,36`) — what must the budget editing surface become (feeds the map's fog on UI)?
- Which parts of the answer are spec-level decisions vs implementation-time detail? Keep the spec to the observable contract, not the migration script.

Blocked by [01-budget-attributes](01-budget-attributes.md) and [02-budget-states](02-budget-states.md).

## Resolution

Decided 2026-11-04 (grilling, 2 rounds):

1. **Auto-backfill, no admin step**: existing budget-type funding sources are migrated with a fabricated **amount = their historical assignment total** and a fabricated **period = earliest invoice date that assigned this budget in a funding assignment → latest such date**. After migration the "every budget has amount + period" invariant holds unconditionally.
2. **Periods are user-editable after creation** (unlike amounts, which are immutable once the period has started — [What attributes does a budget carry?](01-budget-attributes.md) §3). Since attribution has no date filter (§4), editing a period never changes balances; it only shifts the reporting boundary.
3. **Historical bookings count from day one**: reserved/spent derive automatically from existing rows — no booking backfill, no cutover event. Spent appears from historical paid-invoice assignments, reserved from approved reviews (pre-cutover reviews get their funding-source attribution only via the fabricated assignment history; the review-screen split capture applies to decisions going forward).
4. **No date filtering**: attribution is purely by funding-source link — a booking counts toward whichever budget it references, regardless of dates. Periods stay a reporting/succession boundary; late invoices count naturally (consistent with no-automatic-expiry).
5. **Editing surface**: budget create/edit gains amount, period, over-budget flag, and allowance fields; the surface design itself is [What does the budget UI surface look like?](09-budget-ui.md)'s question.
6. **Spec-level contract, not migration script**: the design doc states the observable contract — at activation every budget-type funding source has amount + period; derived numbers include all history — and leaves the migration mechanics to implementation.

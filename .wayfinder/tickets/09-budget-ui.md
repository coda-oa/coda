---
label: wayfinder:prototype
status: closed
assignee: marcus
blocked-by: []
---

# What does the budget UI surface look like?

## Question

Graduated from the map's fog now that attributes, states, capacity, transfers, and placement are decided. The budget system touches four surfaces; a cheap rough artifact (outline, wireframe, or stub) is needed to react to:

1. **Budget overview**: per-budget balances — amount, reserved, spent, credited, debit, available, pending-conversion bucket, exceeded status, period. Filtering/sorting needs?
2. **Budget create/edit form**: unique name, amount (immutable once period starts — how is that surfaced?), mandatory period, "allow going over" flag + optional allowance.
3. **Review-screen extension**: capturing funding source(s) + split for the decided funding amount, with live capacity feedback from the domain check?
4. **Transfer flow**: source/target, amount (incl. debt transfers from exceeded budgets), provenance display.

Constraint from the spec's framing: this is a UI-behavior decision, not pixel design — the prototype should settle what each surface shows and does, not how it's styled. Existing patterns to match: funding-source list/edit views (`src/coda/apps/invoices/views/fundingsources.py`), criteria-based list pages, wizard review step.

**Prototype asset**: [`budget-ui-prototype.html`](../assets/budget-ui-prototype.html) — open the file in a browser; the floating bottom bar (or ←/→ keys) cycles variants per surface; the surface tabs switch between Overview, Create/Edit, Review split, Transfer. Static fake data, verified to render error-free. Variants:
- **Overview**: A dense table (all states as columns) · B master–detail (list + per-budget breakdown with bar and ledger excerpt) · C compact expandable rows.
- **Create/Edit**: A single form with immutability surfaced inline · B two-column with a live state preview.
- **Review split**: A inline split rows with per-row capacity feedback · B capacity bars with allocation state.
- **Transfer**: A plain dialog · B two-step with the ledger rows the transfer will create previewed before booking.

## Resolution

Decided 2026-11-04 from the prototype reaction ([`budget-ui-prototype.html`](../assets/budget-ui-prototype.html) is the primary source):

1. **Overview — follow the existing funding-sources view pattern** (user's call, grounded in `src/coda/apps/invoices/views/fundingsources.py`): a `SimpleSearchEntityListView`-style searchable list of budgets (the existing type=budget filter and name search stay), each row showing name, status chip (within budget / exceeded / pending conversion), and available amount, with the Edit affordance as today. The full state lives on the per-budget **detail page** (extending the existing `FundingSourceDetailView`): all states incl. credited/debit and pending conversion, a spent/reserved/available bar, period, over-budget rule, and the booking-ledger history.
2. **Create/Edit — two-column with live state preview** (variant B): identity/period left; amount (disabled inline once the period started), allow-over flag + allowance, and a live committed/available/pending preview right.
3. **Review split — inline split rows** (variant A): decided amount on top, one row per funding source with amount and live capacity feedback ("fits" / "exceeds: only X available, over-budget not allowed"), save blocked while the split doesn't sum or violates capacity.
4. **Transfer — plain dialog** (variant A): from, to, amount (negative = debt transfer), provenance note. The ledger-preview step from variant B was rejected.

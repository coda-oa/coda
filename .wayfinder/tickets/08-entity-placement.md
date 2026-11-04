---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["02-budget-states"]
---

# Where do budget attributes live?

## Question

Deferred from [What attributes does a budget carry?](01-budget-attributes.md): *where* do the settled attributes (amount, period, over-budget flag + allowance) live?

- Extend the existing `Budget` FundingSource (domain dataclass `src/coda/domain/finance/funding_sources.py:9-22`, DB row `src/coda/apps/invoices/models.py:11-18`) with the new fields — keeping every existing `FundingAssignment` FK and UI filter untouched — or introduce a separate per-period accounting entity linked to the FundingSource, so one funding source can hold several sequential period-budgets?
- If a separate entity: may one funding source's periods overlap or nest? What does "the budget of this funding source" mean at a point in time (for reservations created today against a funding source that has two period-budgets)?
- Whatever the shape: how do existing funding-source references (FR → publication → position → FundingAssignment → FundingSource) resolve to the *right* period's budget?

Deciding this before the state model is known was judged premature; balances and bookings hang off the entity shape, so the state semantics ([What do budget states mean and when do they apply?](02-budget-states.md)) come first, then this ticket reconciles them.

## Resolution

Decided 2026-11-04 (grilling, 1 round):

1. **Attributes live directly on the FundingSource**: amount, period, over-budget flag, and allowance become fields on the existing `Budget` domain dataclass (`src/coda/domain/finance/funding_sources.py:9-22`) and the `FundingSource` DB row (`src/coda/apps/invoices/models.py:11-18`). One funding source = one budget = one period; a new period means creating a new budget (consistent with no-automatic-expiry). The overlap/nesting sub-question dissolves: there is no entity that spans periods, so no period-resolution rule is needed anywhere — attribution stays "by funding-source link, no date filter" exactly as decided.
2. **No formal successor link**: period succession is visible through transfer provenance (old → new transfers, incl. the overrun-as-debit case). No lifecycle to maintain.
3. **Consequences for the spec**: DB row carries per-type integrity (budget-type rows always have amount + period; institution-type rows unaffected — the existing nullable-shared-table pattern continues); name uniqueness applies among budget-type sources; every reference (FundingAssignment FK, review split, transfers, ledger rows, UI filters) keeps pointing at the one entity, unchanged.

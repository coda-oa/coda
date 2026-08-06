# Wayfinder Map: Budget Allocation & Monitoring

> **Labels**: `wayfinder:map`
> **Maturity**: Charting (fog remains — tickets specify what's sharp)

---

## Destination

A budget monitoring feature scoped to the financial context. Each budget has a monetary ceiling (amount + currency + year). Unpaid invoices with budget-linked funding assignments **reserve** on the budget; paid invoices **deduct**. Rejected invoices have no effect. The budget detail page shows total, reserved, deducted, and available amounts, **computed on-the-fly** from invoice data, with warnings for unconvertible multi-currency amounts and oversubscription.

The map is done when every decision needed to build this feature is resolved — aggregate boundaries, link design, UI spec, and lifecycle are all settled. Building the feature itself is a separate effort.

---

## Notes

- **Domain**: Academic publishing finance — article processing charges, subscription fees, institutional funding
- **Stack**: Django, DDD with domain/services/contexts layers (src/coda/domain/, src/coda/apps/, src/coda/contexts/)
- **Budget is a NEW model** — separate from the existing `FundingSource(type="budget")`. Existing records are treated as budget *references*, not the entity itself.
- **Budget is NOT part of the invoice aggregate** — it's a separate aggregate root.
- **Compute budget state on-the-fly** — no materialized ledger for now (query-time aggregation).
- **Warn on oversubscription** — don't block.
- **Warn on unconvertible multi-currency amounts** — show which amounts can't be factored into reserved/deducted.
- **Skills to consult**: domain-modeling, grilling
- **Tracker**: local-markdown (`docs/wayfinding/budget-allocation-monitoring/`)

---

## Decisions so far

- [01 — Exchange Rate Data Sources & Conversion Capabilities](tickets/01-exchange-rate-conversion-capabilities.md) — All rates are entered manually per invoice (stored in `CurrencyConversion`). No automated provider exists; `CachingCurrencyExchange` is unused in production. Home currency = `GlobalPreferences.home_currency` (default EUR). Budget model needs its own `currency` field for per-budget-currency conversion checks.

---

## Not yet specified

The following areas are visible but not sharp enough to ticket. They graduate as the frontier advances.

- **Exact design of Budget-to-FundingAssignment link** — FK vs value object (budget_id + name)? How do we ensure the budget reference is immutable on the assignment once set? This is the central modeling question.
- **Budget CRUD lifecycle** — Who creates budgets? Are they created manually, imported, or derived? Can they be edited/deleted? What happens to assignments when a budget is deleted?
- **Budget detail page layout** — Columns, data display, filtering, sorting. We know what numbers to show but not the wireframe.
- **Budget list/index page** — Navigation to the detail page. Do we need a budget overview first, or just direct URLs for now?
- **Migration strategy** — What happens to existing `FundingSource(type="budget")` records and their `FundingAssignment` links?
- **Currency conversion mechanism** — The system stores per-invoice conversion rates. What happens when a rate isn't available for a needed currency pair? Can we surface all currencies in play?
- **Budget ownership** — Standalone, or belongs to an institution/department/cost center?
- **Budget.currency** — Single currency per budget, or could a budget have multiple currencies?

---

## Out of scope

Ruled beyond this destination:

- **Institution-type FundingAssignments** — These are external contributors outside our financial responsibility; excluded from budget computation.
- **Materialized ledger / BudgetTransaction model** — Deferred; on-the-fly computation is sufficient for now.
- **Period enforcement / auto-close of budgets** — Year is a label, not enforced.
- **Budget approval workflows** — No sign-off gates.
- **Exchange rate live fetching** — Rates are entered manually per invoice; no auto-fetch.

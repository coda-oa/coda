---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: []
---

# What attributes does a budget carry?

## Question

What attributes does a budget (a FundingSource with `type=budget`) carry, and how do they attach to the existing `Budget` domain class and `FundingSource` DB model?

From the source discussion, candidates are: money amount, period, whether going over budget is allowed ("different for types of budgets"?), whether the budget expires at end of period. Open sub-decisions:

- Amount + currency: one currency per budget? (Money value objects refuse cross-currency ops; invoices can be paid in foreign currency.)
- Period: what granularity, is it mandatory, what does it mean for bookkeeping (calendar vs arbitrary range)?
- Is the over-budget allowance an attribute of the budget, and is the discussion's "different for types of budgets" a real second budget kind or just per-budget flags?
- What stays on the existing `Budget`/`FundingSource` vs moves to a new accounting entity hanging off it?
- Name/uniqueness constraints for budgets.

Grounding: `src/coda/domain/finance/funding_sources.py:9-22` (Budget = id + name only), `src/coda/apps/invoices/models.py:11-18` (type/name/institution FK).

## Resolution

Decided 2026-11-04 (grilling, 3 rounds):

1. **Amount & currency**: a budget carries exactly one money amount — the total for its whole period — in the **system-wide currency** (one global setting; not chosen per budget; EUR is the natural default value of that setting). Bookings in other currencies are converted at booking time using the existing `Money`/`CurrencyExchange` machinery.
2. **Period**: mandatory start/end date range, arbitrary ranges (not calendar-aligned). Consequence: every budget has an amount and a period; "budget without an amount" does not exist. Periods remain user-editable after creation (settled later in [How do existing budgets and assignments map onto the new model?](06-backcompat-migration.md) §2); amounts do not.
3. **Amount immutability**: the amount cannot be edited once the period has started. Corrections happen via transfers to another budget or a new budget — never by editing the running total.
4. **Over-budget attribute**: no distinct budget kinds; each budget has a flag "allow going over" plus an optional overage allowance (empty = unbounded when allowed). Enforcement semantics are [What happens when a budget goes over?](03-over-budget.md)'s question.
5. **Expiry**: period end does **not** hard-close a budget — invoices for a budget may arrive after the period has ended and must remain bookable. Detailed expiry design is deferred to [How do budgets expire and transfer to a new budget?](04-expiry-transfers.md), which owns it and records this constraint as a settled input.
6. **Transferability**: governed by uniform rules for all budgets, not a per-budget attribute (conditions live in 04-expiry-transfers).
7. **Names**: budget names are unique.
8. **Deferred**: *where* these attributes live (extend the existing `Budget` FundingSource vs a separate per-period accounting entity, and whether one funding source's periods may overlap/nest) — spun off as [Where do budget attributes live?](08-entity-placement.md), blocked until the state model is known.

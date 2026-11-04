---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["01-budget-attributes", "02-budget-states"]
---

# What happens when a budget goes over?

## Question

Over-budget policy, per the discussion's edge cases:

- If going over is **allowed**: the budget is marked exceeded — what does "exceeded" mean operationally (a state? a flag? derived?), and **how much is one allowed to exceed** (unbounded? a configurable overage allowance?). Does exceeding affect what can still be reserved?
- If going over is **not allowed**: the budget "cannot be used to pay invoices or as funding source for decided funding amount in funding requests". Where is that enforced in the existing workflows — position funding assignment (`src/coda/domain/finance/invoice_positions.py:183-216` currently only validates per-position split sums), funding request approval, or invoice payment? What happens to in-flight funding requests/invoices when a budget runs dry mid-flight?
- Is the allowance per-budget or per budget kind? — **settled** by [What attributes does a budget carry?](01-budget-attributes.md): per-budget flag "allow going over" + optional overage allowance (empty = unbounded when allowed); no distinct budget kinds. What remains here is *enforcement*.

Blocked by [01-budget-attributes](01-budget-attributes.md) (allowance attribute) and [02-budget-states](02-budget-states.md) (exceeded interacts with reserved/spent states).

## Resolution

Decided 2026-11-04 (grilling, 2 rounds):

1. **Exceeded is derived**: a budget displays as exceeded whenever reserved + spent − credited − debit > amount. Nothing persisted, consistent with the derived-balance decision in 02-budget-states.
2. **One uniform capacity rule** at every commitment point: a new commitment is allowed iff reserved + spent + new ≤ amount + allowance — where an empty allowance means unbounded when "allow going over" is set, and no allowance means the amount itself when not allowed. Existing commitments are never revoked by the rule. Outgoing positive transfers count as commitments on the source (see [How do budgets expire and transfer to a new budget?](04-expiry-transfers.md) §5); debt transfers and incoming transfers are exempt.
3. **Enforced at commitment time only**: FR approval (decided-funding reservation, incl. the funding-source split recorded there) and invoice funding assignment. Paying an already-assigned invoice always proceeds — the money is committed and a real bank payment cannot be undone by coda. Today's per-position split validation (`sum ≤ position cost`, `src/coda/domain/finance/invoice_positions.py:183-216`) is unchanged and orthogonal.
4. **Exhausted budget, invoice arrives (not allowed to go over)**: the assignment is blocked. Remedies: assign a different budget, or move funds via transfer/new budget first (amounts are immutable, so topping up the running budget is not an option). The invoice may be entered with unassigned costs — coda already permits that and blocks *payment* on unassigned costs (`UnassignedCosts`, `src/coda/domain/finance/invoice.py:118-121`), so nothing gets paid from nowhere.
5. **Rate-pending bookings are invisible to the capacity check**: it counts only converted amounts; foreign-currency bookings awaiting their bank rate do not constrain new commitments. Accepted risk, chosen deliberately: available is overstated until rates are entered, so silent over-commitment is possible in that window.

---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["02-budget-states", "03-over-budget"]
---

# How do budgets expire and transfer to a new budget?

## Question

Transfer semantics from the discussion's edge cases:

Settled inputs from [What attributes does a budget carry?](01-budget-attributes.md): amounts are immutable once a period starts, so **corrections happen only via transfers or a new budget**; transferability follows **uniform rules** for all budgets (no per-budget flag); period end does **not** hard-close a budget — **invoices arriving after the period has ended must remain bookable**, and the detailed expiry design (what expiry/period end actually does) is this ticket's to decide.

- Transfers of remaining amounts to a new budget are "only allowed after period end if budget does not expire" — what does expiry actually do (close the budget? zero it? keep it readable for reporting)? What are the preconditions for a transfer?
- If the old budget is **exceeded**, the exceeded amount is booked as **debit** on the new budget; the old budget remains exceeded, and the spent amount on the new budget is listed as source in "debit". Unpack this into a precise ledger rule: what exactly is booked where, and does the new budget's available amount shrink by the debit?
- Transferring from a budget **with available funds**: the amount is listed as **debit** on the old budget and **credited** on the new budget. Confirm and pin down: is debit an amount booked against the old budget's books, credited an amount booked to the new one's, and do partial transfers exist?
- Are transfers to *existing* budgets allowed, or only to newly created ones? Multiple transfers out of one old budget?

Blocked by [02-budget-states](02-budget-states.md) (needs credited/debit defined) and [03-over-budget](03-over-budget.md) (exceeded transfer case).

## Resolution

Decided 2026-11-04 (grilling, 2 rounds):

1. **No automatic expiry**: nothing happens at period end. The budget stays fully usable (new commitments, late invoice bookings) until someone acts; the period is purely a reporting boundary. Starting a new period = manually creating a successor budget and transferring. This supersedes the discussion's "transfers only after period end".
2. **Transfers any time**: mid-period included — required anyway because immutable amounts make transfer the only correction mechanism.
3. **Any target, any number**: transfers go to any budget (existing or new); a budget may transfer out multiple times and receive from many sources; negative remainders (an exceeded budget's overrun) are transferable.
4. **One uniform mechanism**: a transfer entry carries amount (possibly negative), source, target, and provenance.
   - *Available-funds transfer*: books **debit** on the source (available drops) and **credited** on the target.
   - *Exceeded-source transfer*: books the overrun as **debit** on the target (inherited debt, available reduced); the source stays exceeded, and the debit's provenance records the source budget plus the spent amounts composing the overrun.
5. **Capacity rule vs transfers**: outgoing *positive* transfers are subject to the source's capacity rule from [What happens when a budget goes over?](03-over-budget.md) — reserved + spent + outgoing ≤ amount + allowance — so a budget not allowed to go over cannot be driven below zero by transferring out. *Debt transfers* (negative amounts, an exceeded budget's overrun) are exempt. Incoming transfers are never blocked: a target may end up exceeded and displays it, derived like any other status.

---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["01-budget-attributes"]
---

# What do budget states mean and when do they apply?

## Question

The discussion proposes budget booking states: **available** (default), **reserved**, **spent**, **credited** — and a transfer concept **debit**. Define each state precisely and when a booking enters/leaves it:

- **Reserved**: discussion says reserved = decided funding amount from approved funding requests OR unpaid invoice, with **unpaid invoice winning over the funding-request amount**. Why the precedence, and what exactly does "wins" mean (replaces the reserved amount? caps it?)? How is reserved computed given the indirect link FR → publication → position → FundingAssignment → FundingSource (`src/coda/apps/fundingrequests/fundingrequest_query.py:264-268`)? What happens when a review is revised, waived, or rejected?
- **Spent**: discussion says paid invoices. Does spent supersede reserved on payment, and how do currency conversions factor in?
- **Credited**: only mentioned via transfers so far — is there any other path to credited (refunds, credit notes)?
- **Available**: amount − reserved − spent ± credited/debit? — note [What attributes does a budget carry?](01-budget-attributes.md) settled that every budget has an amount and a mandatory period, so available is always defined in terms of a concrete amount.
- Are these states of *bookings* (transactions) or derived *balances* of a budget? The discussion mixes both.

Blocked by [01-budget-attributes](01-budget-attributes.md) (available/reserved arithmetic needs the amount/period attributes).

## Resolution

Decided 2026-11-04 (grilling, 3 rounds):

1. **Derived, not booked**: reserved and spent are always computed from existing rows (review results and decided amounts, invoice payment status, funding assignments). No new tables for them; revise/waive/reject a review and reserved recomputes with no reversal logic. The only persisted budget records are **transfers** (debit/credited entries) — existing rows can't represent them.
2. **Reserved**: decided funding of approved FRs. When an unpaid invoice exists, the invoice's assigned amount **replaces** the FR's decided funding (the concrete commitment wins, in either direction). Waived/rejected FRs reserve nothing.
3. **FR budget attribution**: at approval time the review records the intended funding source(s) and their split for the decided amount — a new explicit FR→funding-source link. Reservations exist before any invoice arrives; the indirect FR → publication → position → FundingAssignment path is no longer the only attribution route.
4. **Spent**: paying an invoice converts its reserved portion into spent; the FR reservation it covered is released simultaneously — reserved and spent never overlap for the same money. Unassigned invoice costs (payment already blocked on them, `src/coda/domain/finance/invoice.py:118-121`) never touch a budget.
5. **Credited**: arises only from incoming transfers in v1; refunds/credit notes are not modeled.
6. **Available** = amount − reserved − spent + credited − debit. Whether it may go negative is [What happens when a budget goes over?](03-over-budget.md)'s question.
7. **Currency**: budget currency is the system-wide setting. Bookings are stored in their original currency. The bank conversion rate is **not known when an invoice arrives** (workflow: invoice arrives → paid externally → entered in CODA rateless → bank books at a real rate → rate entered in CODA). Rate-pending bookings are therefore **excluded from converted balances** and shown as a separate **pending-conversion** amount (in original currency); available looks higher than reality until the rate is entered. Conversion uses the entered bank rate, not an event-date rate.

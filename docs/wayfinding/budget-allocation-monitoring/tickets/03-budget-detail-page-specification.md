# 03 — Budget Detail Page Specification

- **Type**: `grilling` (HITL)
- **Status**: Open
- **Blocked by**: (none)

---

## Question

We need the budget detail page wireframe.

**Already settled:**
- Shows: total (ceiling), reserved, deducted, available
- Computed on-the-fly
- Warning banner for oversubscription (reserved + deducted > total)
- Warning for unconvertible multi-currency amounts

**Open questions:**

1. **Layout**: What's the visual hierarchy? Card header with summary numbers and a table below? Or summary at top, breakdown sections below?

2. **Table of contributing invoices**: Do we list every invoice with budget allocations, with columns like:
   - Invoice #
   - Creditor
   - Position description
   - Assigned amount
   - Invoice status (Unpaid → reserved, Paid → deducted)
   - Currency / conversion status?

3. **Filtering / sorting**: Any needed? (by status, by amount, by date)

4. **Unconvertible amounts**: Do we show them in a separate section ("Pending conversion: 3 invoices in EUR/GBP") or inline with a warning icon?

5. **Navigation**: How do users get to this page? From a budget list? From an invoice?

6. **Actions**: Any actions on this page (edit budget, view invoice, etc.)?

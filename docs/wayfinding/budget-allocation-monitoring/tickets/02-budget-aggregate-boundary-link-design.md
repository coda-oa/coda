# 02 — Budget Aggregate Boundary & FundingAssignment Link Design

- **Type**: `grilling` (HITL)
- **Status**: Open
- **Blocked by**: (none)

---

## Question

This is the central modeling question for the entire feature. We need to decide exactly how `Budget` (the new aggregate root) relates to `FundingAssignment` (the existing entity on `Position`).

Key constraints already settled:
- Budget is a **separate aggregate root** — NOT part of the invoice aggregate.
- FundingAssignment is **part of the Position / Invoice aggregate**.
- The link between them must be navigable from both sides (given a budget, find its assignments; given an assignment, find its budget).
- Existing `FundingSource(type="budget")` records exist — they're budget *references*, not the budget entity.

Design options include:

**Option A — FK from FundingAssignment to Budget**
`FundingAssignment.budget = ForeignKey(Budget, null=True)` (nullable because institution splits don't link to a budget).
- Pro: Direct query path, referential integrity, simple.
- Con: Crosses aggregate boundary (Invoice aggregate references Budget aggregate via FK). Acceptable in Django if managed carefully.

**Option B — Value object reference on FundingAssignment**
`FundingAssignment.budget_ref = BudgetReference(budget_id, budget_name)` stored as JSON or embedded fields.
- Pro: Clean aggregate boundary — Invoice aggregate doesn't FK to Budget. Budget reference is an immutable snapshot.
- Con: No referential integrity; need to handle stale references if Budget is renamed.

**Option C — FK from FundingSource to Budget**
Keep the existing chain: `FundingAssignment → FundingSource → Budget` (new FK on FundingSource).
- Pro: Minimal change to FundingAssignment. Reuses existing structure.
- Con: FundingSource becomes a join table. Adds complexity to the chain.

**What we need to decide:**
1. Which option (or hybrid)?
2. If Option B (value object), what fields does `BudgetReference` carry?
3. If Option A or C (FK), how do we ensure the invoice service doesn't modify Budget (aggregate boundary)?
4. Are Budgets themselves editable (name, amount)? Does a rename propagate backward to existing assignments?

Resolving this ticket unblocks Ticket 04 (Budget Lifecycle & CRUD).

# 04 — Budget Lifecycle & CRUD

- **Type**: `grilling` (HITL)
- **Status**: Open
- **Blocked by**: Ticket 02 (Budget Aggregate Boundary & Link Design)

---

## Question

How are budgets created, edited, and deleted?

1. **Creation**: How are budgets brought into the system? Manually via a form? Imported? Derived from funding requests?

2. **Fields at creation**: Name, amount, currency, year — anything else? (e.g., description, institution owner)

3. **Editing**: Can a budget's ceiling (amount) change after invoices have been allocated to it? What about the name?

4. **Deletion**: Can a budget be deleted if it has active FundingAssignments? Cascade? Prevent? Archive/soft-delete?

5. **Listing**: Do we need a budget list page? If so, what columns?

6. **Audit trail**: Do we need to track who changed a budget's amount and when?

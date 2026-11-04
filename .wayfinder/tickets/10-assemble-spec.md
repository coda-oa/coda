---
label: wayfinder:task
status: closed
assignee: marcus
blocked-by: ["09-budget-ui"]
---

# Assemble the budget-system design spec

## Question

Every decision ticket on this map is closed; this is the destination deliverable. Compile the resolutions into the single design doc the map's Destination names:

`docs/design/budget-system.md`, covering:

1. **Domain model** — attributes on the Budget FundingSource (08-entity-placement), per-type DB integrity, unique names (01-budget-attributes).
2. **State model** — derived reserved/spent, invoice-wins rule, reserved→spent on payment, credited via transfers, available formula, pending-conversion bucket (02-budget-states).
3. **Over-budget policy** — derived exceeded status, uniform capacity rule, commitment-time enforcement, exhausted-budget handling, rate-pending blindness (03-over-budget).
4. **Expiry & transfers** — no automatic expiry, uniform transfer mechanism, debit/credited ledger rules, capacity vs transfers (04-expiry-transfers).
5. **Integration & architecture** — SQL read model, domain capacity check, contexts/finance services, review-screen split capture, transfer persistence, booking ledger (05-integration-points, 07-monitoring-data-requirements).
6. **Back-compat** — auto-backfill contract, editable periods, no date filter (06-backcompat-migration).
7. **UI surface** — outcomes of [What does the budget UI surface look like?](09-budget-ui.md).
8. **Monitoring hand-off** — the gap list from 07-monitoring-data-requirements §4 as inputs to the future monitoring effort.

Acceptance: the doc states observable behavior, not implementation mechanics; every section traces to a ticket resolution; `GLOSSARY.md` terms are used consistently. Writing this doc *is* the work — no new decisions should surface; if one does, it goes back on the map as a ticket first.

## Resolution

2026-11-04: the spec is written — [`docs/design/budget-system.md`](../../docs/design/budget-system.md) — covering all eight planned sections, each tracing to its ticket, terms consistent with `GLOSSARY.md`, observable behavior without implementation mechanics. No new decisions surfaced during assembly. The map's destination is reached.

---
label: wayfinder:grilling
status: closed
assignee: marcus
blocked-by: ["02-budget-states"]
---

# What must the budget model record for future monitoring?

## Question

The monitoring use cases themselves are out of scope (separate future effort), but the budget data model must not preclude them. Decide the **data requirements** only:

- The discussion lists: spend per author per period, distributions across institutions, subject areas, journals/publishers, license/OA type, contracts, funding organizations, publication counts by type. For each: does the budget model need to record anything *extra* beyond what existing rows already carry (publication → position → FundingAssignment → FundingSource, contract FK on Position, institution on FundingSource/institution hierarchy in opencost aggregation)?
- Concretely: is per-booking provenance (which invoice/position/FR produced a reserved/spent amount) required by the state model anyway, and does keeping it satisfy the monitoring needs?
- Anything the discussion's use cases need that today's schema can't answer even in principle (e.g. author attribution on spend)?

Keep the answer as a checklist the design spec can cite, not a reporting spec. Grounding: opencost aggregation machinery `src/coda/apps/opencost/data_aggregation.py`, invoice/FR query criteria `src/coda/apps/invoices/invoice_query.py`, `src/coda/apps/fundingrequests/fundingrequest_query.py`.

Blocked by [02-budget-states](02-budget-states.md).

## Resolution

Decided 2026-11-04 (grilling, 2 rounds, grounded in a schema audit):

1. **A persisted booking ledger exists** (chosen over provenance-in-derivation): budget-relevant events are appended as ledger rows at commitment (decided funding recorded, funding assignment created/changed), payment (invoice paid), and transfer (created). Each row: budget, amount in original currency, source-row reference, timestamp. Balance truth remains the derivation; the ledger is the auditable history, independent of it. Writes happen in the same `contexts/finance` service calls — no event listeners (consistent with 05-integration-points §6).
2. **References only, no snapshots**: ledger rows carry source-row references; author/institution/subject/journal attribution joins live rows at reporting time. Converted values stay derived — ledger rows keep original-currency amounts, and entering a bank rate changes derived numbers, not ledger rows.
3. **The budget model needs nothing extra for the monitoring dimensions** — the schema already carries: structured relevant authors (name, ORCID, affiliation FK), subject area + publication type (controlled vocabularies: DFG, COAR), journal/publisher FKs, OA type + license enums (on Publication), contracts (+ contract year, on Position), funding organizations (FR side, with ROR/DOI links), publication states/dates. The ledger's source references make all of it joinable from money.
4. **Known gaps, flagged for the future monitoring effort — explicitly not budget-model requirements**: per-author spend attribution (money attaches to Position; no author FK; non-relevant authors are free text), submitted institution is derived (corresponding-author affiliation or global home institution), not stored on Publication/FundingRequest, OA type/license exist per publication, not per invoice position, publication/contract dates are nullable (period slicing has holes).
5. **Spec checklist**: the design doc states (a) the ledger's event list and row shape, (b) that monitoring dimensions need no new budget-model recording, (c) the gap list above as inputs to the future monitoring effort.

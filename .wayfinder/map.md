# Budget System Design

<!-- wayfinder map · label: wayfinder:map · tracker: local markdown (.wayfinder/) -->

## Destination

A written design spec for the coda budget system — one document (e.g. `docs/design/budget-system.md`) covering the budget domain model, its state model, over-budget policy, expiry/transfer semantics, integration points in existing workflows, and migration/back-compat — ready to hand to implementation planning. Nothing is built by this map.

## Notes

- **Domain**: a budget in CODA is a FundingSource with `type=budget` (settled premise; the only decision taken before this map). Today `Budget` carries only a `name` — no amount, period, or balance exists anywhere in the codebase.
- **Skills every session should consult**: `grilling` and `domain-modeling` (tickets are conversations; glossary terms get written as they crystallize — there is no GLOSSARY.md yet).
- **Grounding facts** (scout brief, file:line):
  - `Budget` funding source: `src/coda/domain/finance/funding_sources.py:9-22`; DB `src/coda/apps/invoices/models.py:11-18`.
  - Decided funding amount on `FundingRequestReview.decided_funding`: `src/coda/domain/fundingrequest/review.py:20-38`.
  - Invoice payment states `Paid/Unpaid/Rejected`: `src/coda/domain/finance/invoice.py:16-20`; per-position splits via `FundingAssignment`: `src/coda/domain/finance/invoice_positions.py:125-216`.
  - FR → funding source link is indirect: FR → publication → position → FundingAssignment → FundingSource (`src/coda/apps/fundingrequests/fundingrequest_query.py:264-268`).
  - Money value objects: `src/coda/domain/money/_money.py` (`Money`, `Currency`, cross-currency ops refused).
- **Standing preferences**: plan-only map (decisions, not deliverables); single design doc as destination; back-compat for existing amount-less budgets is in scope; monitoring use cases are a separate future effort (see Out of scope).
- **Source discussion**: [Budget Overview and Monitoring in CODA](https://github.com/coda-oa/coda/discussions/287).
- **Tracker convention**: open tickets are files in `.wayfinder/tickets/` without `status: closed`; claim by setting `assignee:`; blocking via `blocked-by:` names. The frontier is open, unassigned tickets whose blockers are all closed.

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [What attributes does a budget carry?](tickets/01-budget-attributes.md): one amount (total for a mandatory date-range period, immutable once started) in a system-wide currency; unique names; per-budget over-budget flag + optional allowance; no budget kinds; period end doesn't hard-close (late invoices stay bookable); uniform transfer rules; entity placement deferred to [Where do budget attributes live?](tickets/08-entity-placement.md).
- [What do budget states mean and when do they apply?](tickets/02-budget-states.md): reserved/spent are derived from existing rows (only transfers persist); reserved = decided funding of approved FRs, replaced by an unpaid invoice's assigned amount; approval records funding source(s) + split on the review (new FR→funding-source link); paying converts reserved to spent and releases the FR reservation; credited = transfers only; available = amount − reserved − spent + credited − debit; rate-pending bookings sit in a pending-conversion bucket outside converted balances.
- [What happens when a budget goes over?](tickets/03-over-budget.md): exceeded is a derived status; one uniform capacity rule (reserved + spent + new ≤ amount + allowance, empty = unbounded when allowed) enforced at commitment time only (FR approval, funding assignment), never at payment; exhausted budget blocks assignment until reassignment or transfer; rate-pending bookings are invisible to the capacity check (accepted over-commitment risk).
- [How do budgets expire and transfer to a new budget?](tickets/04-expiry-transfers.md): no automatic expiry — period end is a reporting boundary, successors are manual; transfers allowed any time, to any budget, any number; one uniform transfer-entry mechanism (amount/source/target/provenance: debit on source, credited on target, overrun inherited as debit with provenance); outgoing positive transfers obey the source's capacity rule, debt transfers and incoming transfers are exempt.
- [Where do budget state changes hook into existing workflows?](tickets/05-integration-points.md): SQL read-model query service in `apps/invoices` for balances; pure domain function for the capacity check; `contexts/finance` service owns enforcement (called by review + assignment flows); FR→funding-source split captured on the existing review screen; transfers persist in `apps/invoices` with services in `contexts/finance`; no event listeners, no reversal logic.
- [How do existing budgets and assignments map onto the new model?](tickets/06-backcompat-migration.md): auto-backfill — existing budgets get fabricated amount (historical assignment total) and period (earliest → latest assigning-invoice date); periods stay user-editable (amounts don't); historical bookings count from day one via derivation, attributed by funding-source link with no date filter; the spec states the observable contract, not migration mechanics.
- [What must the budget model record for future monitoring?](tickets/07-monitoring-data-requirements.md): a persisted booking ledger (commitment/payment/transfer rows: budget, original-currency amount, source ref, timestamp) written by the same service calls; references only, no dimension snapshots; the schema already carries every monitoring dimension — remaining gaps (per-author spend, stored submitted institution, position-level OA type, nullable dates) belong to the future monitoring effort.
- [Where do budget attributes live?](tickets/08-entity-placement.md): directly on the Budget FundingSource — one funding source = one budget = one period; new periods mean new budgets; no successor link (transfer provenance shows succession); no period-resolution anywhere; per-type DB integrity, names unique among budgets.
- [What does the budget UI surface look like?](tickets/09-budget-ui.md): overview follows the existing funding-sources searchable-list pattern with per-budget detail pages; create/edit two-column with live preview; review split as inline rows with live capacity feedback; transfer as a plain dialog. Prototype: [`budget-ui-prototype.html`](assets/budget-ui-prototype.html).
- [Assemble the budget-system design spec](tickets/10-assemble-spec.md): the destination — [`docs/design/budget-system.md`](../../docs/design/budget-system.md) compiles all resolutions into the hand-off spec. **Map complete: the way is clear, no open tickets remain.**

## Not yet specified

<!-- empty: every fog patch has graduated or resolved; the route to the destination is clear -->

## Out of scope

- **Monitoring/reporting use cases** (spend by author, distributions by institution/subject area/journal/license/contract/funder): separate future effort; only the data-requirements question is in scope (ticket 07).
- **Implementation of the budget feature**: this map produces a spec; models, migrations, UI are built afterward, outside the map.

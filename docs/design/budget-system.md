# Budget System Design

Status: draft for implementation planning · 2026-11-04
Origin: [Budget Overview and Monitoring in CODA (discussion #287)](https://github.com/coda-oa/coda/discussions/287), resolved through the wayfinder map in `.wayfinder/`. Decisions trace to the tickets linked per section. Terms follow [`GLOSSARY.md`](../../GLOSSARY.md).

## 1. Scope and premise

A **budget** is a funding source of type `budget`. The budget system adds accounting to these sources: an amount with a period, derived balances (reserved / spent / credited / debit / available), a capacity rule, transfers between budgets, and a persisted booking ledger. It does not change institution-type funding sources except where noted. Monitoring/reporting is a separate future effort (§9); this spec only ensures the model does not preclude it.

## 2. Domain model — attributes of a budget

*Ticket: [01-budget-attributes](../../.wayfinder/tickets/01-budget-attributes.md), [08-entity-placement](../../.wayfinder/tickets/08-entity-placement.md)*

A budget carries, directly on the existing `Budget` FundingSource (domain dataclass `src/coda/domain/finance/funding_sources.py`, DB row `src/coda/apps/invoices/models.py`):

| Attribute | Rule |
|---|---|
| **Name** | Mandatory, **unique among budget-type sources**. |
| **Amount** | One money amount — the total for the whole period — in the **system-wide currency** (one global setting; EUR is the natural default). Bookings in other currencies are converted with the existing `Money`/`CurrencyExchange` machinery (§3.5). |
| **Period** | Mandatory start/end date range, arbitrary ranges (not calendar-aligned). **User-editable after creation**; editing never changes balances (attribution has no date filter, §7). |
| **Allow going over** | Per-budget flag. |
| **Overage allowance** | Optional amount; empty = **unbounded** when going over is allowed. |

- **Amount immutability**: the amount cannot be edited once the period has started. Corrections happen only via transfers or a new budget.
- **One funding source = one budget = one period.** A new period means creating a new budget. There is no entity spanning periods and therefore no period-resolution rule anywhere.
- **No formal successor link**: period succession is visible through transfer provenance.
- **No distinct budget kinds**; the discussion's "different for types of budgets" is satisfied by per-budget configuration.
- Per-type DB integrity: budget-type rows always have amount + period; institution-type rows are unaffected (the existing nullable shared-table pattern continues). All references — `FundingAssignment` FK, review split, transfers, ledger rows, UI filters — keep pointing at the one entity.

## 3. State model — budget balances

*Ticket: [02-budget-states](../../.wayfinder/tickets/02-budget-states.md)*

**Reserved and spent are derived**, always computed from existing rows. Only **transfers** are persisted budget records (plus the booking ledger, §6.5). Deriving means: revising, waiving, or rejecting a review recomputes reservations with no reversal logic; nothing subscribes to workflow events.

| State | Meaning |
|---|---|
| **Reserved** | Decided funding of approved funding requests. When an unpaid invoice exists, the invoice's assigned amount **replaces** the FR's decided funding — the concrete commitment wins, in either direction. Waived/rejected FRs reserve nothing. |
| **Spent** | Paid invoices. Paying converts the invoice's reserved portion into spent and releases the FR reservation it covered; reserved and spent never overlap for the same money. Unassigned invoice costs never touch a budget (payment is already blocked on them, `UnassignedCosts`). |
| **Credited** | Money added by an incoming transfer. Transfers are the only source in v1; refunds/credit notes are not modeled. |
| **Debit** | Money booked against a budget by a transfer: leaving it, or an exceeded budget's inherited overrun (§5). |
| **Available** | `amount − reserved − spent + credited − debit`. |
| **Exceeded** | Derived status: `reserved + spent − credited + debit > amount` (§4). Nothing persisted. |

**FR→funding-source attribution**: at approval time the review records the intended funding source(s) and their split for the decided amount — a new explicit FR→funding-source link. Reservations exist before any invoice arrives; the indirect FR → publication → position → FundingAssignment path is no longer the only attribution route.

**Currency — pending conversion**: the bank conversion rate is not known when an invoice arrives (workflow: invoice arrives → paid externally → entered in CODA rateless → bank books at a real rate → rate entered in CODA). Rate-pending bookings are stored in their original currency, **excluded from converted balances**, and shown as a separate **pending-conversion** amount (in original currency). Available therefore looks higher than reality until rates are entered. Conversion uses the entered bank rate, not an event-date rate.

## 4. Over-budget policy

*Ticket: [03-over-budget](../../.wayfinder/tickets/03-over-budget.md)*

- **Exceeded is derived** (see §3); no flag to maintain.
- **One uniform capacity rule** at every commitment point: a new commitment is allowed iff `reserved + spent + new ≤ amount + allowance` — empty allowance = unbounded when "allow going over" is set; no allowance = the amount itself when not allowed. Existing commitments are never revoked by the rule. Outgoing positive transfers count as commitments on the source (§5); debt transfers and incoming transfers are exempt.
- **Enforced at commitment time only**: FR approval (decided-funding reservation incl. its split) and invoice funding assignment. Paying an already-assigned invoice always proceeds — the money is committed and a real bank payment cannot be undone by CODA. The per-position split validation (`sum ≤ position cost`) is unchanged and orthogonal.
- **Exhausted budget, invoice arrives (not allowed to go over)**: the assignment is blocked. Remedies: assign a different budget, or move funds via transfer/new budget first (amounts are immutable; topping up a running budget is not possible). The invoice may be entered with unassigned costs — payment stays blocked on them.
- **Rate-pending bookings are invisible to the capacity check** (it counts only converted amounts). Accepted risk, chosen deliberately: available is overstated until rates are entered, so silent over-commitment is possible in that window.

## 5. Expiry and transfers

*Ticket: [04-expiry-transfers](../../.wayfinder/tickets/04-expiry-transfers.md)*

- **No automatic expiry**: nothing happens at period end. Budgets stay fully usable (new commitments, late-arriving invoices) until someone acts; the period is a reporting boundary. Starting a new period = manually creating a successor budget and transferring. This supersedes the discussion's "transfers only after period end".
- **Transfers are allowed any time**, mid-period included — immutable amounts make transfer the only correction mechanism.
- **Any target, any number**: transfers go to any budget (existing or new); a budget may transfer out multiple times and receive from many sources; negative remainders are transferable.
- **One uniform mechanism** — a transfer entry carries amount (possibly negative), source, target, and provenance:
  - *Available-funds transfer*: books **debit** on the source (available drops) and **credited** on the target.
  - *Exceeded-source transfer*: books the overrun as **debit** on the target (inherited debt, available reduced); the source stays exceeded, and the debit's provenance records the source budget plus the spent amounts composing the overrun.
- **Capacity rule vs transfers**: outgoing positive transfers obey the source's capacity rule — a budget not allowed to go over cannot be driven below zero by transferring out. Debt transfers (negative amounts) are exempt. Incoming transfers are never blocked; a target may end up exceeded and displays it, derived like any other status.

## 6. Integration and architecture

*Tickets: [05-integration-points](../../.wayfinder/tickets/05-integration-points.md), [07-monitoring-data-requirements](../../.wayfinder/tickets/07-monitoring-data-requirements.md)*

House rule: view → query service → service (`contexts/`) → repository (`apps/`) → DB; the domain layer stays Django-free.

1. **Balance overview — SQL read model**: a query service in `apps/invoices` (sibling of `invoice_query`/`fundingrequest_query`) aggregates reserved/spent/credited/debit per budget in SQL and maps to `Money`/DTOs. No Python-side row loops.
2. **Capacity check — pure domain function**: at commitment time the check runs over one budget's bookings (small row set) as a Django-free domain function.
3. **Enforcement — contexts service**: a `contexts/finance` service owns the capacity rule and is called by the funding-request review flow and the invoice assignment flow. Views never check budgets directly.
4. **FR→funding-source split capture**: on the existing review screen (already separate from the create/update wizards), alongside the decided funding amount.
5. **Booking ledger — persisted**: budget-relevant events are appended as ledger rows at commitment (decided funding recorded, funding assignment created/changed), payment (invoice paid), and transfer (created). Each row: budget, amount in original currency, source-row reference, timestamp. Balance truth remains the derivation; the ledger is the auditable history. Writes happen in the same `contexts/finance` service calls — no event listeners. Ledger rows carry source references only, no dimension snapshots; entering a bank rate changes derived numbers, never ledger rows. The ledger is **append-only event history**: editing an assignment or re-approving a review appends a further row rather than updating one, and balances are never computed from ledger rows.
6. **Transfers — `apps/invoices`**: transfer entries persist next to `FundingSource` (new model + migrations); transfer services in `contexts/finance`. No new Django app.
7. **No event listeners, no reversal logic** anywhere else.

## 7. Back-compat and migration

*Ticket: [06-backcompat-migration](../../.wayfinder/tickets/06-backcompat-migration.md)*

- **Auto-backfill, no admin step**: existing budget-type funding sources are migrated with a fabricated **amount = their historical assignment total** and a fabricated **period = earliest invoice date that assigned this budget in a funding assignment → latest such date**. After migration, "every budget has amount + period" holds unconditionally.
- **Invoice import creates placeholder budgets**: when import encounters a funding-source name with no budget, it creates one with amount 0 and an unbounded period until a user sets real attributes via the budget edit surface. The DB check constraint (authored after the backfill migration) guarantees the columns are present. **Enforcement surfaces**: the capacity rule applies to *review decisions* and *manual/UI funding assignments*; invoice import is a recorded fact and does not run the capacity check. An import-created placeholder budget therefore has zero available by design — committing to it from a review or the assignment UI is rejected until a user configures its amount. "Unconfigured" is not a separate state; amount 0 *means* zero capacity.
- **Historical bookings count from day one**: derived balances automatically include existing rows — spent from historical paid-invoice assignments, reserved from approved reviews (pre-cutover reviews get attribution via the fabricated assignment history; the review-screen split applies to decisions going forward). No booking backfill, no cutover event.
- **No date filtering**: attribution is purely by funding-source link; a booking counts toward whichever budget it references, regardless of dates. Periods stay a reporting/succession boundary; late invoices count naturally.
- The spec states this observable contract, not migration mechanics.

## 8. UI surface

*Ticket: [09-budget-ui](../../.wayfinder/tickets/09-budget-ui.md); prototype: [`.wayfinder/assets/budget-ui-prototype.html`](../../.wayfinder/assets/budget-ui-prototype.html)*

1. **Budget overview** — follows the existing funding-sources pattern: a searchable list view (existing `type=budget` filter and name search stay), rows showing name, status chip (within budget / exceeded / pending conversion), and available amount, with the Edit affordance as today. The full state lives on the per-budget **detail page** (extending `FundingSourceDetailView`): all states incl. credited/debit and pending conversion, a spent/reserved/available bar, period, over-budget rule, and the booking-ledger history.
2. **Create/Edit** — two-column: identity/period left; amount (disabled inline once the period started, with the immutability explanation), allow-over flag + allowance, and a live committed/available/pending preview right.
3. **Review screen** — decided amount on top; one attribution row per funding source with amount and live capacity feedback ("fits" / "exceeds: only X available, over-budget not allowed"); save blocked while the split doesn't sum to the decided amount or violates capacity.
4. **Transfer** — plain dialog: from, to, amount (negative = debt transfer), provenance note.

## 9. Monitoring hand-off (future effort, out of scope here)

The schema already carries every dimension the discussion's monitoring use cases need (structured relevant authors with ORCID + affiliation, subject area and publication type via controlled vocabularies, journal/publisher FKs, OA type + license enums, contracts with contract year, funding organizations with ROR/DOI links, publication states/dates); the ledger's source references make them joinable from money. Known gaps the monitoring effort must solve — **not** budget-model requirements:

- Per-author spend attribution: money attaches to positions; no author FK; non-relevant authors are free text.
- Submitted institution is derived (corresponding-author affiliation or global home institution), not stored on Publication/FundingRequest.
- OA type/license exist per publication, not per invoice position.
- Publication/contract dates are nullable; period slicing by those dates has holes.

## 10. Open items for implementation planning

None carried over from the map. Implementation-level choices deliberately left open: exact DTO shapes, migration mechanics, check-constraint details, and the system-wide currency setting's configuration surface.

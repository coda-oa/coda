# Budget System Design

Status: implemented · 2026-11-04 (spec), 2026-11-05 (implementation, incl. cost-basis amendment (ADR [0001](../adr/0001-budget-cost-basis.md)) and import ledger booking)
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

**Cost basis (ADR [0001](../adr/0001-budget-cost-basis.md))**: budgets commit **gross-of-tax** amounts — the money that actually leaves the bank. Positions state their costs **net-of-tax** with the tax rate on the position row; the gross figure is derived as `amount × (1 + tax_rate)` wherever the budget subsystem consumes it. VAT-type cost rows self-handle (stored rate 0, full cost in `cost_amount`). Review-split reservations carry no rate; their decided amount counts as gross by definition. Rate-pending bookings are grossed in their original currency before conversion. Derived amounts are rounded per row, ROUND_HALF_UP, to the currency's minor units — matching `Money` — so capacity decisions and ledger rows never disagree. Display stays net-of-tax.

**Currency — pending conversion**: the bank conversion rate is not known when an invoice arrives (workflow: invoice arrives → paid externally → entered in CODA rateless → bank books at a real rate → rate entered in CODA). Rate-pending bookings are stored in their original currency, **excluded from converted balances**, and shown as a separate **pending-conversion** amount (in original currency). Available therefore looks higher than reality until rates are entered. Conversion uses the entered bank rate, not an event-date rate.

## 4. Over-budget policy

*Ticket: [03-over-budget](../../.wayfinder/tickets/03-over-budget.md)*

- **Exceeded is derived** (see §3); no flag to maintain.
- **One uniform capacity rule** at every commitment point: a new commitment is allowed iff `reserved + spent + new ≤ amount + allowance` — empty allowance = unbounded when "allow going over" is set; no allowance = the amount itself when not allowed. Existing commitments are never revoked by the rule. Outgoing positive transfers count as commitments on the source (§5); debt transfers and incoming transfers are exempt.
- **Enforced at commitment time only**: FR approval (decided-funding reservation incl. its split) and invoice funding assignment. Paying an already-assigned invoice always proceeds — the money is committed and a real bank payment cannot be undone by CODA. The per-position split validation (`sum ≤ position cost`) is unchanged and orthogonal.
- **Exhausted budget, invoice arrives (not allowed to go over)**: the assignment is blocked. Remedies: assign a different budget, or move funds via transfer/new budget first (amounts are immutable; topping up a running budget is not possible). The invoice may be entered with unassigned costs — payment stays blocked on them.
- **Rate-pending bookings are invisible to the capacity check** (it counts only converted amounts). Accepted risk, chosen deliberately: available is overstated until rates are entered, so silent over-commitment is possible in that window.

*Amendments during implementation (2026-11-05)*:
- **Cost basis (ADR [0001](../adr/0001-budget-cost-basis.md), §3)**: budgets commit gross-of-tax amounts; the capacity check's delta and its persisted-totals snapshot switch basis together — a mixed pair would silently re-introduce the re-save double-count. The review-side check is already gross-consistent (splits carry the decided amount as-is).
- **Invoice re-saves check only the delta** (spec §4 "existing commitments are never re-checked", made concrete): `ensure_assignment_capacity` compares each assignment against the invoice's own persisted per-budget totals and checks only positive differences. Without this, re-saving an existing invoice — via the edit view or the pay view — counted its own commitment twice and raised on fully-committed budgets.
- **The HTMX add-assignment view does not check capacity**: an assignment there is a draft until the invoice is saved. Capacity errors surface at save time: the create/update views catch the `DomainError`, show it as an inline message, and re-render the form with the entered data; nothing is persisted.
- **Commitment ledger rows book once per assignment**: a re-save that leaves an assignment unchanged (same budget, cost currency, amount) books no further row; only new or changed assignments do.

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

1. **Balance overview — SQL read model**: a query service in `apps/invoices` (sibling of `invoice_query`/`fundingrequest_query`) aggregates reserved/spent/credited/debit per budget in SQL and maps to `Money`/DTOs. No Python-side row loops. **Cost basis**: assignment-derived rows are grossed in SQL as `amount × (1 + position.tax_rate)` (VAT rows self-handle — stored rate 0); review-split rows take their decided amount as-is, gross by definition; each row is rounded to its own currency's minor units, ROUND_HALF_UP, matching `Money`, so capacity decisions and ledger rows never disagree.
2. **Capacity check — pure domain function**: at commitment time the check runs over one budget's bookings (small row set) as a Django-free domain function.
3. **Enforcement — contexts service**: a `contexts/finance` service owns the capacity rule and is called by the funding-request review flow and the invoice assignment flow. Views never check budgets directly.
4. **FR→funding-source split capture**: on the existing review screen (already separate from the create/update wizards), alongside the decided funding amount.
5. **Booking ledger — persisted**: budget-relevant events are appended as ledger rows at commitment (decided funding recorded, funding assignment created/changed), payment (invoice paid), and transfer (created). Each row: budget, **gross-of-tax amount in the original currency**, source-row reference, timestamp. Balance truth remains the derivation; the ledger is the auditable history. Writes happen in the same `contexts/finance` service calls — no event listeners. **Invoice import books rows too**: the import path bypasses the capacity check (§7) but calls the same ledger writers, so imported invoices — including ones arriving paid — leave a complete audit trail. Ledger rows carry source references only, no dimension snapshots; entering a bank rate changes derived numbers, never ledger rows. The ledger is **append-only event history**: editing an assignment or re-approving a review appends a further row rather than updating one, and balances are never computed from le…
6. **Transfers — `apps/invoices`**: transfer entries persist next to `FundingSource` (new model + migrations); transfer services in `contexts/finance`. No new Django app.
7. **No event listeners, no reversal logic** anywhere else.

## 7. Back-compat and migration

*Ticket: [06-backcompat-migration](../../.wayfinder/tickets/06-backcompat-migration.md)*

- **Auto-backfill, no admin step**: existing budget-type funding sources are migrated with a fabricated **amount = their historical assignment total** and a fabricated **period = earliest invoice date that assigned this budget in a funding assignment → latest such date**. After migration, "every budget has amount + period" holds unconditionally.
- **Invoice import creates placeholder budgets**: when import encounters a funding-source name with no budget, it creates one with amount 0 and an unbounded period until a user sets real attributes via the budget edit surface. The DB check constraint (authored after the backfill migration) guarantees the columns are present. **Enforcement surfaces**: the capacity rule applies to *review decisions* and *manual/UI funding assignments*; invoice import is a recorded fact and does not run the capacity check — but it **does book ledger rows** (commitments, and payments for imports arriving paid), so its balance movements stay auditable (§6.5). An import-created placeholder budget therefore has zero available by design — committing to it from a review or the assignment UI is rejected until a user configures its amount. "Unconfigured" is not a separate state; amount 0 *means* zero capacity.
- **Historical bookings count from day one**: derived balances automatically include existing rows — spent from historical paid-invoice assignments, reserved from approved reviews (pre-cutover reviews get attribution via the fabricated assignment history; the review-screen split applies to decisions going forward). No booking backfill, no cutover event.
- **No date filtering**: attribution is purely by funding-source link; a booking counts toward whichever budget it references, regardless of dates. Periods stay a reporting/succession boundary; late invoices count naturally.
- The spec states this observable contract, not migration mechanics.

## 8. UI surface

*Ticket: [09-budget-ui](../../.wayfinder/tickets/09-budget-ui.md); prototype: [`.wayfinder/assets/budget-ui-prototype.html`](../../.wayfinder/assets/budget-ui-prototype.html). Amended 2026-11-05 by the [Budget UI Completion map](../../.wayfinder/map.md): items 1.1–1.4 and 3.1–3.3 below; prototypes: [`budget-detail-progress-prototype.html`](../../.wayfinder/assets/budget-detail-progress-prototype.html), [`review-split-affordance-prototype.html`](../../.wayfinder/assets/review-split-affordance-prototype.html).*

1. **Budget overview** — follows the existing funding-sources pattern: a searchable list view (existing `type=budget` filter and name search stay), rows showing name, status chip (within budget / exceeded / pending conversion), and available amount, with the Edit affordance as today. The full state lives on the per-budget **detail page** (extending `FundingSourceDetailView`): all states incl. credited/debit and pending conversion, the balance overview per **1.1**, period, over-budget rule, and the booking-ledger history.
    - **1.1 Balance overview (progress bar)** — the detail page leads with a big colored **Available (gross-of-tax)** figure beside a slim stacked bar of `spent` (red) and `reserved` (amber) out of the amount; secondary line "of ⟨amount⟩ gross-of-tax (+ allowance)". **Pending conversion is an annotation, not a segment** (original currency, excluded from available — §3). Exceeded budgets: the available figure turns red; the bar caps at full width — no overfull segment, the red figure carries the state (matching the list's `exceeded` chip). New CSS primitive `.budget-balance-bar` in `components.css`. All figures gross-of-tax (ADR 0001); labels carry the qualifier.
    - **1.2 Invoice reference list** — the detail page lists the invoices whose **current** `FundingAssignment`s reference the source (existing `FundingSourceCriterion` in `invoice_query`), as the **invoice number linking to the invoice detail** — no further columns; the 10 most recent, plus an "All invoices for this funding source →" link to the invoice list pre-filtered by this source. No date filtering (§7).
    - **1.3 Budget list navigation** — the list row's **name links to the detail page** (house pattern, as the institutions list); "Edit" stays beside it.
    - **1.4 Institution rows have no funding-source detail page** — institution funding sources are implicit byproducts of funding assignments to an institution, never managed by hand; they never appear on the funding-source list (`type="budget"` filter). `FundingSourceDetailView` **and** `FundingSourceUpdateView` redirect institution rows to the linked `Institution`'s detail page (fallback `institutions:list` if the FK is missing; soft-deleted institutions still render — `Institution.all_objects`). The detail template's institution branch is deleted; the funding-source detail is budget-only by construction.
2. **Create/Edit** — two-column: identity/period left; amount (disabled inline once the period started, with the immutability explanation), allow-over flag + allowance, and a live committed/available/pending preview right.
3. **Review screen** — decided amount on top; one attribution row per funding source with amount and live capacity feedback ("fits" / "exceeds: only X gross-of-tax available, over-budget not allowed"); save blocked while the split doesn't sum to the decided amount or violates capacity — rendered per **3.1**–**3.3**.
    - **3.1 Split table** — the attribution section is a **table** (Funding source | Amount (gross-of-tax) | Gross left (all splits) | remove) with an "+ Add funding source" button above and a footer sum row with a live verdict ("matches the decided amount ✓" / "difference X"). "Gross left" aggregates **all rows on that budget**, not just the row — matching `ensure_capacity`'s sibling-summing. Capacity feedback is **live on change**, gross-of-tax-qualified.
    - **3.2 Add-row mechanism** — hand-wired into the review POST flow: the add button submits the review form with a `form_action_add` marker; `review.py` checks it **before** `action` handling and re-renders the full page with one more form row (full page context, "Available per budget" included). No new URL, no `htmx_components` `ManagementView` wiring. All figures gross-of-tax; labels carry the qualifier.
    - **3.3 Attribution is mandatory on approval** — **defect fix**: today `_validate_splits` returns early when no splits exist, silently approving decided funding > 0 with zero attribution (nothing reserved). Approval must reject when the splits don't sum to the decided funding, **including the zero-splits case**; zero decided funding with zero splits stays valid.
4. **Transfer** — an **inline form on the budget detail page**: from, to, amount (negative = debt transfer), provenance note. "Plain dialog" in the original text meant *no wizard*, not a modal — the shipped form (`detail.html` + `budget_transfer` POST) is the contract. Entry stays on the detail page (the list row's name links there — 1.3); no list-level transfer affordance.

## 9. Monitoring hand-off (future effort, out of scope here)

The schema already carries every dimension the discussion's monitoring use cases need (structured relevant authors with ORCID + affiliation, subject area and publication type via controlled vocabularies, journal/publisher FKs, OA type + license enums, contracts with contract year, funding organizations with ROR/DOI links, publication states/dates); the ledger's source references make them joinable from money. Known gaps the monitoring effort must solve — **not** budget-model requirements:

- Per-author spend attribution: money attaches to positions; no author FK; non-relevant authors are free text.
- Submitted institution is derived (corresponding-author affiliation or global home institution), not stored on Publication/FundingRequest.
- OA type/license exist per publication, not per invoice position.
- Publication/contract dates are nullable; period slicing by those dates has holes.

## 10. Open items for implementation planning

None carried over from the map. Implementation-level choices deliberately left open: exact DTO shapes, migration mechanics, check-constraint details, and the system-wide currency setting's configuration surface.

# Budget System — TDD Test Plan

Planning document, no code. Companion to [`budget-system.md`](budget-system.md). Test names use `GLOSSARY.md` vocabulary. Loop discipline per the tdd skill: red → green, one vertical slice per cycle, refactoring deferred to review.

**Confirmed 2026-11-04**: all seven seams approved; S7 asserts targeted HTML fragments (error messages, chips, states — not full-page snapshots); migration/backfill milestone F included.

**Amended during execution**:
- B and D reordered: D1 (S5 round-trip) pulled forward because S3's literal assertions need the persisted budget columns; D1 drove the schema, migration `invoices/0026` (columns only), `FundingSourceDomainMapper`, and the repository paths.
- The budget check constraint is deferred to Milestone F (authored after the backfill migration) — applying it before backfill would violate on real databases holding name-only import rows.
- B3 narrowed to the invoice-only half of the reservation rule: an unpaid invoice's assignment counts as **reserved** (available drops). The full precedence — "unpaid invoice **replaces decided funding**", plus "paying releases the FR reservation" — lives in the **read model** (not only in E's write path), pinned by B-cycles in the same slice that introduces the `ReviewFundingSplit` table: per FR+budget, assignments (unpaid → reserved, paid → spent) win over review splits; the split counts only for FRs with no assignments on that budget. Without this, `capacity_verdict` double-counts and rejects valid review decisions.
- The read model sums assignments per `position.cost_currency`: budget-currency amounts count directly; foreign-currency amounts land in the pending-conversion bucket (converted once the bank rate is entered, B-cycle later in this milestone). `FundingAssignment.amount` carries no currency of its own.
- Capacity check functions return a `CapacityVerdict(allowed, available_after)` — **no exception, no message field**. `available_after` is always populated (negative = how far the commitment goes past the limit); Milestone C composes its `DomainError` text and Milestone G renders "exceeds: only X available" from that number.

## Mocking policy

Mock at system boundaries only — and this feature has **none**: no external APIs, no time/randomness asserted, no filesystem. The database is real (pytest-django). **The plan is mock-free.** Everything is tested through real interfaces: domain functions called directly, services called with real repositories, views exercised via the Django test client.

## Seams (the pre-agreed test surface)

Seven seams, ordered from purest to outermost. Each notes what it catches and what it misses.

| # | Module | Seam (public interface) | Level | Catches | Misses |
|---|---|---|---|---|---|
| S1 | `domain/finance/budget_capacity.py` | `check_capacity(bookings, new, allow_over, allowance)` raising `CapacityExceeded` | pure pytest, no Django | The whole capacity rule matrix: over allowed/not, allowance empty/set, boundary equality, outgoing transfers as source commitments, debt-transfer exemption | Wiring, persistence, whether callers actually call it |
| S2 | `domain/finance/` (transfer rules + `DateRange` value object + amount-immutability rule) | `create_transfer_rules(...)` / period helpers as pure functions | pure pytest | Debit/credited bookkeeping semantics, debt-transfer exemption, period validity | Persistence |
| S3 | `apps/invoices/budget_query.py` | `budget_balances(funding_source_id)` → `BudgetBalanceDto` (reserved / spent / credited / debit / available / pending conversion) | pytest-django, real DB | Derivation correctness: unpaid-invoice-wins, reserved→spent on payment, waived/rejected reserve nothing, pending-conversion bucket excluded from available, credited/debit from transfers | Aggregation performance at scale; UI |
| S4 | `contexts/finance/services/budget_service.py` | `ensure_capacity(id, amount)`, `record_decided_funding(...)` (split validation + capacity + ledger write), `create_transfer(...)` | pytest-django through real repositories | Rule enforcement through the stack; sum-of-splits validation; ledger rows appear per event; error modes surface as typed exceptions | HTTP layer, form parsing |
| S5 | `apps/invoices/funding_source_repository.py` + `mappers/_domain.py` | repository create/update/get round-trips for `Budget` with new attributes; name-uniqueness constraint | pytest-django | Persistence round-trip; partial unique constraint fires; institution sources unaffected | Domain rules (covered by S1/S2) |
| S6 | `contexts/fundingrequest/services/fundingrequests.py` `update_review` | review submission with funding splits | pytest-django | Split recorded on approval; revision recomputes reservations with no reversal logic; sum mismatch rejected; capacity violation rejected | Form rendering |
| S7 | Django views (test client) | POST `fundingrequests:review` with splits; HTMX `invoices:position_add_funding_assignment` with over-capacity amount; `invoices:budget_transfer`; budget list/detail pages | pytest-django + test client, HTML assertions | User-visible behavior: inline "exceeds: only X available" errors, blocked save, status chips, pending-conversion display, ledger history rendering | Business rules (asserted only via their visible effect — the rules live at S1–S4) |

Deliberately **not** tested: DTO `to_post_data` plumbing, form field declarations, template internals beyond rendered HTML, query counts (except the existing suite stays green), anything derivable by construction.

## TDD cycle sequence (vertical slices, one test per cycle)

### Milestone A — capacity domain (S1, S2)

Tracer bullets in order:

1. `test_capacity_allows_commitment_within_amount` — budget 100, committed 60, new 40 → passes. *(red: module doesn't exist)*
2. `test_capacity_rejects_commitment_beyond_amount_when_over_not_allowed` — new 41 → `CapacityExceeded`.
3. `test_capacity_allows_commitment_beyond_amount_when_over_allowed_without_allowance`.
4. `test_capacity_allows_commitment_up_to_allowance_when_over_allowed` — amount 100 + allowance 50, committed 140, new 10 → passes.
5. `test_capacity_rejects_commitment_beyond_allowance_when_over_allowed`.
6. `test_capacity_counts_outgoing_transfer_as_source_commitment` (S2 rule folded into bookings).
7. `test_debt_transfer_is_exempt_from_capacity` — negative amount never rejected.

Each cycle: write the failing test with a literal expected outcome (worked example, never recomputed), implement only enough of `check_capacity` to pass, next.

### Milestone B — balance read model (S3)

1. `test_available_equals_amount_minus_committed` — seeded invoice + assignment, paid; expect literal `BudgetBalanceDto` values.
2. `test_approved_review_reserves_its_split_before_any_invoice` (needs M4 table seeded directly — factory-created, not via service).
3. `test_unpaid_invoice_replaces_decided_funding_in_reserved` — both present; reserved = invoice assignment amount (literal).
4. `test_waived_review_reserves_nothing`.
5. `test_paying_invoice_moves_reservation_to_spent` — same seed, paid after; reserved drops, spent rises by the same literal.
6. `test_unassigned_invoice_costs_never_touch_budget`.
7. `test_foreign_currency_without_conversion_is_pending_and_excluded_from_available`.
8. `test_entering_conversion_rate_moves_amount_out_of_pending`.
9. `test_transfer_books_debit_on_source_and_credited_on_target` (after M-transfers).
10. `test_exceeded_budget_transfers_overrun_as_debit_on_target`.

### Milestone C — enforcement service (S4)

1. `test_ensure_capacity_raises_for_exhausted_budget` — service over seeded DB state.
2. `test_record_decided_funding_rejects_split_not_summing_to_decided_amount`.
3. `test_record_decided_funding_rejects_split_exceeding_capacity`.
4. `test_record_decided_funding_writes_commitment_ledger_row`.
5. `test_creating_transfer_writes_debit_and_credited_ledger_rows` (two rows, one event each).
6. `test_paying_invoice_writes_payment_ledger_row`.
7. `test_budget_amount_cannot_be_edited_after_period_start` — service guard raises.

### Milestone D — persistence round-trip (S5)

1. `test_budget_round_trips_amount_period_and_over_budget_rules`.
2. `test_budget_names_are_unique_among_budgets` — constraint fires (`IntegrityError`), institution sources unaffected.
3. `test_institution_funding_source_maps_unchanged`.

### Milestone E — review flow (S6)

1. `test_approving_review_with_valid_split_persists_splits` (service-level; S7 covers the POST).
2. `test_revising_review_replaces_splits_without_reversal_logic`.
3. `test_review_split_violating_capacity_blocks_approval`.

### Milestone F — migrations & backfill (django_test_migrations, own DB per `tests/database/conftest.py`)

1. `test_backfill_fabricates_amount_from_assignment_total` — pre-migration seeded rows; migrate; assert literal amount.
2. `test_backfill_fabricates_period_from_first_to_last_assigning_invoice`.
3. `test_backfill_leaves_institution_sources_untouched`.

### Milestone G — user-visible surfaces (S7)

1. `test_review_page_shows_live_capacity_feedback_for_split_rows` — rendered HTML contains the "exceeds: only X available" message for a seeded exhausted budget.
2. `test_assignment_with_over_capacity_amount_is_blocked_with_inline_error`.
3. `test_budget_list_shows_status_chip_and_available` (within budget / exceeded / pending conversion chips).
4. `test_budget_detail_shows_full_state_and_ledger_history`.
5. `test_transfer_dialog_books_a_transfer`.
6. `test_budget_amount_field_is_disabled_after_period_start`.

## Amendment — cost basis (2026-11-05)

**Status: implemented 2026-11-05.** Budgets commit **gross-of-tax** amounts (ADR [`0001`](../adr/0001-budget-cost-basis.md); decisions in the [Budget Cost Basis map](../../.wayfinder/map.md)). Positions state net-of-tax; gross is derived as `amount × (1 + tax_rate)` in the budget subsystem's consumers. Every budget-suite fixture uses `TaxRate.from_percentage(0)` (`budget_setup.py:54`), so **no existing test literal changes** — the amendment is additions plus the gap-disposition items.

### New cycles

1. **Read model (S3)** — `test__assignment_with_tax__reserved_is_gross_of_tax_amount` (worked example: net 1680.6723 @ 19% → gross 2000.00); `test__vat_type_position__books_exactly_its_cost` (stored rate 0 self-handling); `test__pending_conversion__grosses_in_original_currency_then_converts` (one rounding); `test__per_row_rounding__sums_rows_individually` (two rows whose unrounded gross sum ≠ per-row-rounded sum — capacity consumes the per-row figures).
2. **Ledger (C)** — commitment and payment rows book gross in the original currency with a nonzero rate; a VAT row books its cost as-is.
3. **Capacity (C)** — `test__re_saving_taxed_assignment__delta_is_gross_of_tax` (snapshot and delta switch basis together); existing delta tests stay (0% fixtures).
4. **Domain** — `funding_assignments(CostBasis.gross)` returns 2000.00 for the net-stored 1680.6723 (next to the existing net-storage pin; the domain contract is pinned, not flipped).
5. **Gap dispositions (closed tickets)** — uniqueness milestone: partial `UniqueConstraint` (`condition=Q(type="budget")`) with a loud pre-check migration + `migrationtests` milestone, typed service error rendered as a form error, institution sources unaffected; pending-conversion chip list-view test; reinstated B4 `test__waived_review__reserves_nothing` (waived review *with split data attached* reserves nothing, persists no rows).
6. **Import ledger rows** — imported invoice with budget assignment books a commitment row; a paid import books the payment row (import keeps bypassing the capacity check, §7).
7. **Run the export suites after the flip** — `tests/exports/fundingrequest_csv/helpers.py` creates invoices through the capacity-checked path at 19%; "gross still fits the 10000 fixture budget" is an empirical claim, verified by running, not reasoning.

### Explicitly unchanged

Budget-suite literals (0% fixtures); capacity domain tests (basis-agnostic); review-split tests (budget-currency amounts, gross as-is); export/CSV assertions (display stays net); `test_invoice_import.py` (assertions never observe the budget subsystem); the 0029 backfill migration tests (the new constraint migration gets its own `migrationtests` milestone).

## Amendment — budget UI completion (2026-11-05)

Companion to the §8 amendments (`docs/design/budget-system.md`); decisions in the [Budget UI Completion map](../../.wayfinder/map.md). All cycles use the Django test client with targeted HTML-fragment assertions, per the plan's conventions. **Seams under test**: the funding-source list/detail views (rendered HTML), the funding-source form rendering (selects show names — `__str__`), the review POST path (`review.py` `form_valid` — `form_action_add` round-trip, `ReviewSplitFormSet`, `_validate_splits`), and `budget_transfer` (unchanged; only navigation around it changes).

### New cycles

1. **Funding-source rendering** — `test__funding_source__renders_as_name_in_selects` (review-split select and invoice filter sidebar show the name, not "FundingSource object (N)"); institution row shows the institution's label; `test__budget_with_blank_name__renders_pk_label` (budget row, blank name, no institution → pk label, no crash).
2. **Detail page: balance overview** — `test__budget_detail__shows_available_figure_and_balance_bar` (big available figure, slim spent/reserved bar segments, gross-of-tax qualifiers, amount (+allowance) secondary line); `test__budget_detail__exceeded__shows_red_available` (bar capped, red figure); `test__budget_detail__shows_pending_conversion_annotation` (annotation line, not a segment).
3. **Detail page: invoice reference list** — `test__budget_detail__lists_invoices_referencing_the_source` (invoice number links to the invoice detail; 10 most recent; "All invoices" link carries the funding-source filter); `test__budget_detail__ignores_deleted_assignments` (re-saved invoices don't double-list).
4. **List navigation** — `test__budget_list__name_links_to_detail` (row name links to `invoices:fundingsource_detail`).
5. **Institution routes** — `test__institution_source__detail_redirects_to_institution_page`; `test__institution_source__update_redirects_to_institution_page` (both with the soft-deleted-institution case still resolving).
6. **Review screen: split table** — `test__review_page__renders_split_table_with_add_button`; `test__review_page__add_row_round_trips` (POST with `form_action_add` before `action` re-renders with one more row and preserves entered data); `test__review_page__capacity_feedback_is_gross_of_tax_qualified` ("exceeds: only X gross-of-tax available" for an exhausted budget, sibling-aggregated); `test__review_page__sum_verdict_shows_difference` (splits not summing to decided funding show the live difference). **Feedback is server-rendered**: the view/template composes the message from `CapacityVerdict(allowed, available_after)` (no message field on the verdict — the plan's standing rule) on every page render and re-POST, so the Django test client can assert the HTML; client-side on-change updating is an optional enhancement on top, never the thing the tests pin.
7. **Attribution mandatory on approval (defect fix)** — `test__approving_review_without_splits__rejected` (decided funding > 0, zero splits → `InvalidFundingSplit`; today silently accepted — the cycle is red until `_validate_splits` drops its `if not splits: return`); zero decided funding with zero splits stays valid.
8. **Changed behavior — blast radius of 7**: the `_validate_splits` rule change is **Approved-only** — reject/close/waive/return paths are untouched. **Gate**: a full `pdm run unittests` + `pdm run integrationtests` re-run after implementing is mandatory to surface any fixture that approves with an empty `funding_splits` formset — checked 2026-11-05: `tests/fundingrequests/test_review_splits.py` approval cases all post splits, and the wizard tests post no `funding_splits` keys, so expected fallout is small; re-run and confirm rather than assume. A newly-failing fixture **gains splits** — the rule does not relax.

## Amendment — budget review & transfers polish (2026-11-05)

Companion to the §8 amendments (Budget Review & Transfers Polish map). **Seams under test**: the review GET (split prefill) and review POST markers (`form_action_add`/`form_action_remove`/`form_action_refresh` on the **existing review URL** — there is **no new fragment endpoint for live fit**), the review page's per-budget available excluding the review's own splits (opt-in read-model parameter), the re-approval capacity/ledger path in the funding-request service, the FR-detail **read model** (attribution field) plus its rendered HTML, the transfer dialog's **GET fragment endpoint** and its POST fragment error re-render (the existing POST URL), and the balance bar rendering (re-pinned literals). Good tests assert rendered HTML/DTO fields, not internals; prior art: the existing budget view tests and review-split tests.

### New cycles

1. **Review split prefill** — `test__review_page__prefills_persisted_splits` (re-opened approved review renders the persisted budget selected + amount + gross-left figure + sum verdict, not blank; `TOTAL_FORMS` = persisted-row-count + 1); waived/rejected reviews render empty.
2. **Re-approval delta (defect fix)** — `test__re_approval__does_not_double_count_own_splits` (tight-capacity literal: budget 1 000, own split 600, re-submit unchanged → accepted; raise beyond remaining → rejected); `test__re_approval__ledger_dedupes_unchanged_splits` (approve 600, re-approve 600 → ledger net stays 600; re-approve 800 → one further row — re-scopes the old append-only test).
3. **Display exclusion** — `test__review_page__available_excludes_own_persisted_splits` (the review page's per-budget available excludes the review's own split rows; the budget detail page still counts them — default semantics unchanged).
4. **Live fit** — `test__review_page__refresh_round_trips` (POST with `form_action_refresh` before `action` re-renders the page with recomputed feedback and entered data); `test__review_page__refresh_aggregates_sibling_rows` (two rows on one budget → one aggregated "gross left" figure on the live path); the "Available per budget" list is gone from the rendered page.
5. **FR detail attribution** — `test__fundingrequest_detail__shows_funding_attributions` (read model: attribution field carries budget id/name + gross-of-tax amount; HTML: the block lists budget name + amount for an approved review with splits; renders nothing without splits).
6. **Balance bar** — re-pinned literals: zero bookings → full-width available segment (no empty bar); partial → available 55 % + spent 25 % + reserved 20 % inside the pill; exceeded (amount 1 000 / allowance 500 / spent 1 600) → spent 93.75 % + hatched over 6.25 %, red available figure.
7. **Transfer dialog** — `test__transfer_dialog__opens_as_fragment` (GET fragment endpoint renders the `<dialog open>` form); `test__transfer_dialog__error_renders_in_fragment` (a capacity/transfer error re-renders the dialog fragment with the message — the old full-page `transfer_error` assertions migrate); `test__transfer_dialog__add_funds_mode__books_credited_row` (add-funds: no target, positive amount, provenance mandatory → one credited ledger row, available rises; zero/negative rejected); budget-to-budget transfers book two rows as before (the nullable source must not alter them).
8. **Unaffected** — balance read-model, ledger, and capacity suites (the polish renders their figures); invoice reference list; rendering/`__str__` cycles; export suites.

## Conventions

- DB tests: `@pytest.mark.django_db`; run `docker exec -w /app coda_local_django pdm run pytest tests/invoices tests/fundingrequests -q`; `--create-db` after schema changes; parallel-safe (no shared module state, own rows per test).
- Factories extended, not duplicated: `tests/modelfactory.py` (`budget()` gains attributes, plus `review_funding_split`, `budget_transfer`, `ledger_entry`), `tests/domainfactory.py` (`budget()` domain object gains amount/period/flags).
- Pure domain tests live next to the domain package: `tests/domain/finance/` (no `django_db` mark).
- Expected values are always literals or worked examples from the spec — never recomputed via the code under test.

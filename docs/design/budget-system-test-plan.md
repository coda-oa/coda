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

## Conventions

- DB tests: `@pytest.mark.django_db`; run `docker exec -w /app coda_local_django pdm run pytest tests/invoices tests/fundingrequests -q`; `--create-db` after schema changes; parallel-safe (no shared module state, own rows per test).
- Factories extended, not duplicated: `tests/modelfactory.py` (`budget()` gains attributes, plus `review_funding_split`, `budget_transfer`, `ledger_entry`), `tests/domainfactory.py` (`budget()` domain object gains amount/period/flags).
- Pure domain tests live next to the domain package: `tests/domain/finance/` (no `django_db` mark).
- Expected values are always literals or worked examples from the spec — never recomputed via the code under test.

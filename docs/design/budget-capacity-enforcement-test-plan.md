# Budget Capacity Enforcement — TDD Test Plan

Planning document, no code. Companion to [`budget-capacity-enforcement.md`](budget-capacity-enforcement.md). Test names use `GLOSSARY.md` vocabulary. Loop discipline per the tdd skill: red → green, one vertical slice per cycle, refactoring deferred to review.

**Confirmed 2026-11-09**: all six seams approved; `add_test_invoices` routes through the guarded save path; lock/transaction mechanics are review-covered, not test-covered; wizard live feedback rides the existing HTMX responses (no new endpoint); milestone order A→F as below.

## Mocking policy

Mock at system boundaries only — this feature has **none**. The database is real (pytest-django). **The plan is mock-free**: domain functions called directly, services called with real repositories, views exercised via the Django test client, import via the service with real repositories.

## Seams (the pre-agreed test surface)

Six seams, purest to outermost. Each notes what it catches and what it misses.

| # | Module | Seam (public interface) | Level | Catches | Misses |
|---|---|---|---|---|---|
| S1 | `domain/finance/budget_capacity.py` | new `check_commitment_capacity(bookings per budget, deltas per budget)` → verdict per budget, plus the generalized currency-keyed delta function (the `positive_delta` generalization) | pure pytest, no Django | Aggregation rule (sum per budget before checking), per-(budget, currency) keying, positive-only deltas, `allow_over`/`allowance` composition, review-shape behavior preservation | Wiring, persistence, whether callers call it |
| S2 | `contexts/finance/services/budget_service.py` | rewritten `ensure_assignment_capacity(invoice)` (pytest-django through real repositories) | pytest-django | The reported bug both ways: multi-assignment-same-budget joint rejection, edit-delta arithmetic, rate-time converted branch, manual paid invoices, guard-before-persistence | HTTP layer, form parsing |
| S3 | `contexts/fundingrequest/services/fundingrequests.py` `update_review` | review submission after migration onto the primitive | pytest-django | Behavior preservation: the existing suite (re-approval delta, ledger dedupe, capacity rejection) stays green unchanged | Rendering |
| S4 | `contexts/finance/services/invoice_import/_service.py` through real repositories | batch import | pytest-django | Batch-summed per-budget deltas, placeholder exemption (by creation), paid-import counting, whole-batch atomic rejection, converted-amount checking | Upload UI |
| S5 | Django views (test client), targeted HTML fragments | invoice create/update POST, distribution-step HTMX responses, rate recording | pytest-django | Flash errors naming budget + over-amount, live per-budget feedback with in-session sums, red state, converted-only figures, non-blocking rate-overrun warning | Business rules (asserted only via their visible effect) |
| S6 | `add_test_invoices` management command | command run | pytest-django | Command routes through the guarded save path: assignment rows + ledger commitment rows appear; no bypass | — |

Deliberately **not** tested: DTO `to_post_data` plumbing, form field declarations, template internals beyond rendered HTML, and the **lock/transaction mechanics** (decided: `select_for_update` discipline and same-transaction check-and-book are covered by code review against the transfer suite's precedent, `budget_service.py:150-152` — a transaction-introspection test would be implementation-coupled by the tdd skill's own standard). Spec §9 is amended accordingly.

## TDD cycle sequence (vertical slices, one test per cycle)

### Milestone A — shared domain primitive (S1)

Pure tests in `tests/domain/finance/`. Tracer bullets in order:

1. `test__positive_delta__sums_per_budget_and_currency` — worked example: new assignments 60 + 40 on one budget, one currency → one delta of 100; a second currency on the same budget stays a separate key.
2. `test__positive_delta__subtracts_own_persisted_totals` — persisted 60+60, new 100+100 → one positive delta of 80, never two −20s (the edit-delta bug's arithmetic, pinned at the domain).
3. `test__positive_delta__drops_non_positive_deltas` — decrease or unchanged → no key.
4. `test__positive_delta__missing_persisted_totals_count_as_zero`.
5. `test__check_commitment_capacity__returns_one_verdict_per_budget` — deltas on two budgets → two verdicts, judged independently.
6. `test__check_commitment_capacity__aggregated_delta_meeting_limit_exactly_passes` — amount 100, delta 100 → allowed, `available_after` 0.
7. `test__check_commitment_capacity__aggregated_partial_deltas_over_limit_rejected` — the bug's shape: 60 + 60 against 100 → one rejected verdict, `available_after` −20 (not two passing verdicts).
8. `test__check_commitment_capacity__over_allowed_up_to_allowance_then_rejected` — allowance composition per the uniform capacity rule.
9. `test__check_commitment_capacity__unbounded_when_over_allowed_without_allowance`.
10. `test__positive_delta__single_currency_review_shape_unchanged` — feed review splits (one currency) through the generalized function; result identical to the current source-keyed `positive_delta` (behavior-preservation pin for Milestone C).

Each cycle: failing test with a literal expected outcome (worked example, never recomputed), implement only enough of the primitive to pass, next.

### Milestone B — invoice guard (S2)

The reported bug, closed both ways. `tests/invoices/test_budget_service.py` gains cycles; existing tests stay green throughout.

1. `test__invoice_with_two_assignments_to_one_budget__rejected_when_jointly_over` — budget 100, positions 60 + 60 → `BudgetCapacityExceededError` naming the budget and the over-amount. *(red: current per-assignment check lets it pass)*
2. `test__two_assignments_jointly_within_capacity__saved` — 60 + 40 → saved.
3. `test__edit_raising_total_beyond_capacity__rejected` — persisted 60+60 edited to 100+100 against budget 100 → rejected (the edit-delta bug; today the deltas come out −20 and no check runs).
4. `test__edit_lowering_total__passes` — 60+60 → 50+50 → saved without a check.
5. `test__assignment_with_conversion_rate__checked_converted` — foreign-currency position with a recorded rate; converted amount joins the budget's delta; over → rejected.
6. `test__assignment_without_rate__rate_pending_and_skipped` — foreign currency, no rate → saved even against a zero-capacity budget (rate-pending invisibility, per spec §7).
7. `test__manually_entered_paid_invoice_with_rate__checked` — paid status does not exempt manual entry.
8. `test__rejected_save__persists_nothing` — after a rejected save, no assignment rows and no commitment ledger rows exist (guard-before-persistence, asserted through repository state).

### Milestone C — review migration (S3)

**No new tests unless a gap appears.** The migration onto the shared primitive is a refactor: per the tdd skill, refactoring is not part of the red → green loop. The existing suite is the specification — `tests/fundingrequests/test_review_splits.py` (re-approval delta, ledger dedupe) and the review capacity-rejection tests must pass unchanged. Gate: full `pdm run unittests` + `pdm run integrationtests` after the migration. If any review test needs changing, the migration changed behavior — stop and fix the migration, not the test.

### Milestone D — import (S4)

1. `test__import_batch_exceeding_budget__whole_batch_rejected` — two invoices in one batch, 60 + 60 against budget 100 → nothing persisted (atomic rejection), error names budget and over-amount. *(red: import bypasses entirely today)*
2. `test__import_batch_within_capacity__all_invoices_saved`.
3. `test__import_auto_created_placeholder_budget__exempt` — new budget name, placeholder amount 0 → import succeeds; budget later shows exceeded once configured.
4. `test__import_against_pre_existing_zero_amount_budget__checked` — a budget that existed before the run (even amount 0) gets the real check; over → whole batch rejected.
5. `test__paid_imports_count_toward_batch_delta` — batch with paid 80 + unpaid 30 against budget 100 → rejected (paid commitments count; only the paid rows themselves are unblockable).
6. `test__paid_import_alone__never_blocked` — a paid import over capacity imports anyway.
7. `test__import_with_conversion_rates__converted_amounts_checked` — foreign-currency imports carrying rates join the batch delta converted.

### Milestone E — user-visible surfaces (S5)

Test client, targeted HTML-fragment assertions per the prior plan's conventions.

1. `test__create_invoice_over_capacity__flash_error_names_budget_and_over_amount` — POST create over capacity → re-render with the message; no redirect.
2. `test__update_invoice_raising_beyond_capacity__flash_error` — same via the update POST.
3. `test__distribution_step__shows_live_available_per_budget` — HTMX add-assignment response contains the per-budget available figure *after the in-session distribution* (literal: budget 100, in-session 60 → "40 available").
4. `test__distribution_step__feedback_turns_red_when_over` — in-session sums exceed capacity → the red state marker renders (informational; the save still enforces).
5. `test__distribution_step__aggregates_sibling_assignments` — two in-session assignments on one budget → one aggregated figure, not per-row.
6. `test__distribution_step__shows_converted_amounts_only` — foreign-currency position with a rate: the figure is converted; no pending-conversion figure renders in the wizard (the budget page owns that, spec §7).
7. `test__rate_added_to_saved_invoice__proceeds_with_overrun_warning` — save rate-less, then POST the rate that pushes the budget over → save succeeds (delta 0), flash carries the non-blocking "this rate pushes budget X over by N" warning, conversion row persisted, budget renders exceeded.

**Not directly testable, covered by review**: closing `inspect.pay_invoice`'s uncaught `DomainError` (`inspect.py:225-234`). On the pay/reset path the commitment delta is always 0, so no reachable input produces a capacity error there — the uniform catch is hardening, verified by review against the create/update pattern, not by a test.

### Milestone F — management command (S6)

1. `test__add_test_invoices__books_through_the_guarded_path` — run the command; assignment rows and commitment ledger rows both exist for the created invoices (today: ledger rows absent — the observable signal that the bypass is closed).
2. `test__add_test_invoices__fits_the_seeded_budgets` — the command's generated invoices pass the capacity guard against the budgets it uses (the command becomes realistic data, not a rule-breaking backdoor).

## Conventions

- DB tests: `@pytest.mark.django_db`; run `docker exec -w /app coda_local_django pdm run pytest tests/invoices tests/fundingrequests -q` (plus `tests/domain` for Milestone A); parallel-safe (no fixed ports, no shared module state, own rows per test). `--create-db` only if a schema change sneaks in — this effort requires none.
- Factories extended, not duplicated: `tests/domainfactory.py` gains an invoice-with-multiple-assignments builder (positions on one budget, per-position cost currency); `tests/modelfactory.py` gains a pre-existing zero-amount budget where needed for Milestone D.
- Expected values are always literals or worked examples from the spec — never recomputed via the code under test.
- Import cycles seed through the import service's input shape (parsed invoice data), not by poking models.

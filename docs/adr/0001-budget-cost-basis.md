# Budget commitments use gross-of-tax amounts

Budgets must reflect the money that actually leaves the bank, so every budget commitment — invoice-assignment reservations and spent, review-split reservations, ledger rows, and the capacity check — is a **gross-of-tax** amount. Positions state their costs **net-of-tax** with the tax rate on the position row; the gross figure is derived as `amount × (1 + tax_rate)` wherever the budget subsystem consumes it (SQL read model, capacity delta and its persisted-totals snapshot, ledger booking). VAT-type cost rows self-handle: they persist `tax_rate = 0` with the full cost in `cost_amount`, so the expression needs no special case. Storage stays net-of-tax — no schema change and no data migration; balances recompute from the stored rates.

## Considered options

- **Storing gross in `FundingAssignment.amount`** (write-time conversion) was rejected: existing rows are stored net, so it would require a data migration, and exports/CSV that read the column raw would silently change output meaning.
- **Net-of-tax budgets** was rejected: the bank pays gross; and review reservations (which have no rate at all) would mix bases with invoice assignments under the "unpaid invoice replaces decided funding" precedence rule.

## Consequences

- Review-split reservations have no tax context; their decided amount counts as gross by definition (`ReviewFundingSplit.amount`, in the budget's currency).
- The capacity check's delta and its persisted-totals snapshot must always switch basis together; a mixed pair silently re-introduces a double-count on invoice re-save.
- The SQL read model rounds each assignment row's gross amount to its own currency's minor units, ROUND_HALF_UP — matching `Money` — so capacity is evaluated on ledger-identical numbers.
- Derived balances shift for existing data (accepted: the feature is not deployed anywhere); no migration is needed because the rates remain stored.
- Display stays net-of-tax: invoice DTOs, review-screen split rows, position summaries, and exports are untouched; only budget accounting is gross.

Decided 2026-11-05 via the Budget Cost Basis wayfinder map (`.wayfinder/map.md`); vocabulary in `GLOSSARY.md` (cost basis / net-of-tax / gross-of-tax).

# 01 — Exchange Rate Data Sources & Conversion Capabilities

- **Type**: `research` (AFK)
- **Status**: Open
- **Blocked by**: (none)

---

## Question

What exchange rate infrastructure does coda currently have for converting invoice amounts to different currencies? Specifically:

1. How does `CurrencyConversion` work end-to-end? Who provides exchange rates? When are they entered?
2. What currencies are in use across existing invoices and budgets?
3. What happens when a rate isn't available for a needed currency pair? How is "missing conversion" detected and surfaced to users today?
4. How does `CachingCurrencyExchange` get wired into the system (if at all)? Is there an `ExchangeProvider` implementation beyond test stubs?
5. What's the home/base currency used by the system? Where is it configured?
6. How could we surface "unconvertible" invoice amounts for a given budget currency? What data do we need?

Answers inform Ticket 3 (detail page warnings, unconvertible amount display).

---

## Resolution

### 1. CurrencyConversion end-to-end

**Model** (`src/coda/apps/invoices/models.py:99-107`): stores `target_currency` (str, 3), `exchange_rate` (Decimal 11,4), FK to `Invoice`. No `source_currency` — source is implicit (invoice's currency, derived from first position's `cost_currency`). No `date` field.

**Entry paths** — rates entered **manually** in all cases:
- **Manual create** (`views/create.py:24-34`): reads `conversion_currency_<code>` and `exchange_rate_<code>` from POST.
- **Manual update** (`views/update.py:80-109`): iterates `exchange_rate_*` POST keys.
- **Import** (`contexts/finance/services/invoice_import/_parsing.py:134-138`): `ConversionImportDto` from import JSON.

**Persistence** (`mapper.py:303-314`): `_create_currency_conversions()` reads `invoice.conversions()` (dict[Currency, Decimal]) and bulk-creates `CurrencyConversion` rows.

### 2. Currencies in use

EUR is home (default from `GlobalPreferences.home_currency`). USD, JPY, GBP, and many others appear in tests. The `Currency` enum supports ~180 ISO codes.

### 3. Missing detection

`MissingCurrencyConversionCriterion` (`invoice_query.py:109-120`): filters for invoices where `positions__cost_currency ≠ home_currency` AND no `CurrencyConversion` rows exist. Surfaced as `has_foreign_currency` checkbox in invoice list filter bar. At domain level, `invoice.convert(to)` raises `NoSuchConversion` if target currency missing.

### 4. CachingCurrencyExchange

**NOT wired into production.** Only tested (`tests/money/test_cachingcurrencyexchange.py`). No `ExchangeProvider` implementation exists beyond test stubs. All rates are manual.

### 5. Home currency

`GlobalPreferences.home_currency` (default: `Currency.EUR`). Set via admin UI. No Django settings-level config.

### 6. Unconvertible amounts for budget currency

Need data per budget:
- Budget's own currency field (currently `FundingSource` has no currency)
- Position's `cost_currency` per assignment
- Check for `CurrencyConversion` where `target_currency == budget_currency`

**Key implication**: Budget model needs a `currency` field. The existing `MissingCurrencyConversionCriterion` approach can be adapted per-budget-currency.

### Assets

None created beyond this report.


# Funding Request List: Persistent Filter Sidebar

**Date:** 2026-09-01
**Status:** Draft for review
**Scope:** `/fundingrequests/list/` only (not invoices, not a shared component)

## Problem

The advanced filters on the funding request list are a flat `<details>` block with 10 fields in arbitrary order. Concrete issues:

1. No grouping — nothing signals which fields relate.
2. Three different UIs for "pick some values" (bare select, checkbox dropdowns, `search-select-multi`), and the publication-type select has no label.
3. No visibility of active filters once the `<details>` is collapsed; "Clear" nukes everything including the search term.
4. Labels and exclude-labels are two unrelated multi-selects with no shared context.
5. The "invalid contract years" switch and sort sit outside the advanced section.
6. Every change requires an explicit Search click and a full page reload, though HTMX is already loaded on every page.

**Usage pattern (confirmed with user):** most lookups use the plain search box or 1–2 filters; occasionally users build very specific multi-filter queries.

**Behavior decision (confirmed):** filters apply live via HTMX — no Search button.

## Chosen direction

A **persistent, always-visible sidebar** holding all filter controls, grouped into four sections. The list takes the remaining width. **The sidebar sits on the right** so it balances the app's left-hand navigation. This was chosen over:

- **Hybrid (toolbar toggle + collapsible sidebar)** — rejected: a half-open sidebar is the worst of both.
- **Toggleable grid of group cards** — good, but the user preferred filters always within arm's reach during multi-filter sessions.

## Design

### Page layout

```
┌──────────────┬──────────────────────────────────────────────┐
│ Filters (n)  │  [ search box ................ ]  [ sort ▾ ] │
│  Clear all   │  ┌──────────────────────────────────────────┐ │
│              │  │ funding request rows …                   │ │
│ STATUS       │  │                                          │ │
│  Processing  │  └──────────────────────────────────────────┘ │
│  [chips]     │  ‹ 1 2 3 … ›                                  │
│  Payment st. │  (pagination above list stays as today)       │
│  [chips]     │                                               │
│  Method      │                                               │
│  [chips]     │                                               │
│  Open access │                                               │
│  [chips]     │                                               │
│              │                                               │
│ PUBLICATION  │                                               │
│  (All|Art|Mo)│                                               │
│  From / To   │                                               │
│              │                                               │
│ CONTRACT     │                                               │
│  [contract]  │                                               │
│  Year        │                                               │
│  [✓] invalid │                                               │
│              │                                               │
│ LABELS       │                                               │
│  Include     │                                               │
│  [chips]     │                                               │
│  Exclude     │                                               │
│  [chips]     │                                               │
└──────────────┴──────────────────────────────────────────────┘
```

- Sidebar is fixed width (~240–260 px), sticky while scrolling.
- **No chip row** — the sidebar itself is the state display; each control shows its own selected chips. This avoids keeping two representations in sync.
- The title bar (New Article / New Monograph / Import) and pagination stay where they are.

### Sidebar groups and controls

All query-param names are **unchanged** from today, so `fundingrequest_query.py`, `param_replace` consumers (label pills, type icons, pagination), and breadcrumb filter-preservation keep working untouched.

| Group | Control | Current param | New control |
|---|---|---|---|
| Status | Processing status | `processing_status` (multi) | `search-select-multi` |
| Status | Payment status | `payment_status` (multi) | `search-select-multi` (existing partial) |
| Status | Payment method | `payment_methods` (multi) | `search-select-multi` |
| Status | Open access type | `open_access_type` (multi) | `search-select-multi` (existing partial) |
| Publication | Type | `publication_type` (single: `all`/`article`/`monograph`) | 3-way segment (radio inputs, `name="publication_type"`, default `all`) |
| Publication | Date range | `start_date`, `end_date` | native date inputs, side by side |
| Contract | Contract | `contract_name` (single) | `search-select` (existing) |
| Contract | Contract year | `contract_year` (int) | text input |
| Contract | Invalid years only | `invalid_contract_years` (switch) | switch, kept |
| Labels | Include | `labels` (multi) | `search-select-multi` (existing partial) |
| Labels | Exclude | `exclude_labels` (multi) | `search-select-multi` (existing partial) |

Retired: the checkbox-dropdown partials (`status_dropdown.html`, `payment_method.html`) and the bare `publication_type` select. One multi-select control type everywhere.

### Toolbar (above the list)

- Search input (`search_term`) — live, debounced ~300 ms.
- Sort select (`sort_by`) — moved here from the bottom of the form; applies on change.
- No Search button.

### Sidebar header

- "Filters" + count badge = number of active filter **values** across the sidebar fields (each selected chip counts one; e.g. processing:approved + payment:unpaid + label:urgent = 3). `search_term` and `sort_by` are excluded — they are visible in the toolbar. No badge when 0.
- "Clear all" link (shown only when count > 0) → plain GET to the list URL with no params (same as today's Clear link).

### Behavior

- Every change (chip add/remove, segment click, date typed, switch toggled, sort changed, search typed) triggers an HTMX request; the search input debounces ~300 ms, discrete controls fire immediately.
- The list region (entity list + both pagination includes + the "no matches" message) is the swap target; the rest of the page (sidebar, toolbar) is not re-rendered.
- The sidebar's own control state persists because it is not swapped.
- Empty result: keep the existing "No funding requests match the selected filters." message inside the list region, with a "Clear all" link.

### HTMX mechanics

- The whole sidebar + toolbar is one `<form method="get">`.
- The list region div carries `hx-get` to the same list URL with `hx-trigger="change from:form, keyup delay:300ms from:form"` (form = the sidebar/toolbar form), plus `hx-swap` default. The server returns the full page; HTMX swaps only the list region div. No new endpoint needed.
- Pagination links stay plain GET links (they already preserve all filter params); full page loads work without JS.

## Bugs fixed as part of this work

1. `status_dropdown.html` mis-detects multi-value selection (`status in request.GET.processing_status` — substring containment on the first value). Moot once the checkbox dropdowns are retired; the replacement controls use the existing `getlist` template tag correctly.
2. Context typo `exlude_labels` in `listview.py` (`labels` is passed under both keys — fix the name).
3. Verify and fix the `OpenAccessType` name-vs-value mismatch (template passes enum *values*, `OpenAccessTypeCriteria` matches enum *names*; only Opt-in/Opt-out diverge).

## Out of scope

- Migrating the invoices list or any other page.
- A reusable cross-app filter component.
- Narrow-window / mobile behavior for the sidebar (internal desktop tool; note as known limitation).
- Filter presets / saved views.
- Mutual exclusion between label include/exclude selections.

## Testing

- IRON RULE: use skill tdd-reference to write tests and implementation
- **Regression:** the existing end-to-end filter tests (`tests/fundingrequests/test_fundingrequest_search.py`) exercise the query params and must pass unchanged — they are the primary safety net since param names don't move.
- New/updated tests:
  - View context: filter count is computed from active (non-default) params.
  - Segment control submits `publication_type` correctly (including default `all`).
  - Sidebar partial renders with correct preselected values for a multi-value GET.
  - The list region carries the expected HTMX attributes (light template test).
- Manual checklist: live search debounce, chip add/remove, segment, dates, contract + year, switch, include/exclude labels, sort, clear all, empty state, pagination with active filters, back-navigation breadcrumb preserving filters.

## Risks / open items

- **Row width:** the list permanently loses the sidebar's width. Titles already truncate; the row template may need a small pass to keep columns legible (title first, de-emphasize contract/journal columns).
- **Narrow windows:** no collapse rule in v1; accept as a limitation.

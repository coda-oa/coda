# Statistics Tables — CSV Export Plan

Designed, not started. Adds a per-table CSV download to the funding-request statistics page:
one file per dimension section, exporting the section's complete value set — no top-10 cut,
no "Other" fold — with the comparison period's raw values alongside when compare is on.

Two implementation paths exist for the same requirements (§2 compares them):
**Path A** — server-side export endpoint + a client-side disclosure that expands the
"Other" row (§3–§9); **Path B** — DataTables renders the tables and its Buttons extension
produces the CSV client-side (§10). The shared core is identical in both: fact fetch,
unbounded grouping, comparison label join.

**Settled: Path A.** §2's comparison and §10 remain as the recorded alternative and its
evaluation; the path choice is recorded as ADR 0010 (`adr/0010-static-tables-server-csv-export.md`).
Also settled: the expansion reset on every region re-render is accepted;
file conventions per §3 #6 confirmed; the button label is **"Export CSV"**; the money
column is uniformly **`amount`** on every dimension (§6).

## 1. Scope

- One download button per section table (per dimension), not one combined file.
- Rows are the full grouping of that dimension under the page's current filters:
  `aggregation.group_by(facts, dimension, top_n=None)` — the mode the institution treemap
  already uses. Every value keeps its own row; "Other" never appears in an export.
- Comparison values are raw (publications and amount of the prior period), not deltas or
  percentages. The comparison columns exist only when compare is on; within them, a cell is
  blank when the row has no prior counterpart.

Out of scope, deliberately: the treemap (not a table), the timeline/headline figures, a
combined all-dimensions file, persisted exports (the `exports` app pattern), delta/percent
columns, DataTables' server-side processing mode (§10 — it would break the client-side
export and contradict ADR-0004's in-memory aggregation).

## 2. Overview — two implementation paths

The data layer is shared: both paths compute one unbounded grouping per dimension
(`group_by(top_n=None)`) joined label-wise with the comparison grouping. They differ in
where the table's full row set lives and where the CSV is produced.

| Aspect | Path A: server export + disclosure | Path B: DataTables + Buttons CSV |
| --- | --- | --- |
| New dependencies | none | `dataTables.js` + `dataTables.buttons.js` + CSS, vendored (~100 KB; jQuery-free standalone DT 2). Alternative considered and rejected: simple-datatables (§10.0 — no orthogonal export source, LGPL) |
| CSV produced by | server view, pytest-tested pure function | client-side Buttons config; correctness lives in JS/DOM contract |
| Export ↔ table drift | possible in principle, guarded by shared row builder (§9) | impossible — the export *is* the table's data |
| Export columns | declared in the CSV builder | orthogonal-data contract: raw values via `data-sort` (exists) + new `data-*` attributes for raw comparison values; deltas/note/share excluded |
| Table interactivity | static HTML; "Other" expands to the full set (§9) | search, sort, page over the full set — the 1074-journal tail becomes findable |
| "Other" row | kept (folded values in a disclosure) | gone — full table, paged |
| Payload per region render | top-10 + folded rows in hidden HTML | same rows, in DT's data source (`data` option / json_script, the plotly pattern) |
| htmx integration | delegated fold toggle in `reporting.js` only (document-level, no re-init needed) | destroy/re-init on every region swap (`htmx:afterSwap`); state resets unless persisted |
| Chart/table relation | table ⊇ chart's row set (documented relaxation, §9) | table ⊇ chart's row set (chart folds, table paginates) |
| Test surface | server-side pytest: CSV bytes, rows, compare behavior (§11) — unit-level, byte-exact | export assertable in-repo: the reporting page already has a Playwright suite (`tests/reporting/test_reporting_ui.py`, live server), so `page.expect_download` verifies the CSV end-to-end; but the contract under test is the JS config + `data-*` attributes, not a pure function |
| Server work | export view + URL + param pruning (~100–130 lines) | none (only template/JS + new `data-*` attributes) |
| Fails when | — | JS disabled/broken → no table interaction and no export |

Decision guidance: if users must *find* values in the long tail (search "Molecules" among
1074 journals), Path B is the better product and the export comes with it. If the tail only
needs to be *available* (expand, or take the CSV), Path A delivers with zero dependencies
and a tested export artifact. The tail's shape is measured: 1074 distinct journals, 707 of
them with exactly one request — the fold/disclosure exists for that dimension.

## 3. Decisions, and the defaults I took without asking

1. **On-the-fly download, not a persisted export.** The `FundingRequestCSVExport` pattern
   (storage, detail pages, regeneration) buys nothing here: the numbers are derived, cached
   facts are cheap, and the user already has the filters set on the page. Matches the
   institutions export (`apps/institutions/views.py`).
2. **Export mirrors the table, minus the fold.** Same row kinds (VALUE, UNKNOWN,
   UNASSIGNED), same suppression of zero-money rows for the cost-type dimension, same
   label-ordered-by-rank. "Just the tables as they are, complete."
3. **All measures the dimension supports, exactly as the table shows them** — publications
   where the table shows publications (cost type omits the count: a request can hold
   several cost types, so the count would double), spend where it shows spend (funder has
   no money).
4. **Comparison columns appear only when compare is on**; no zero-padding, so a blank cell
   and a zero are distinguishable (a row that did not exist last period vs. one that existed
   with zero).
5. **`login_required`, like the page itself.**
6. **CSV conventions follow the existing exports**: `;` separator, `utf-8-sig` encoding
   (Excel), `Content-Disposition: attachment`, filename `<dimension_id>_export_<timestamp>.csv`.

Defaults to veto any of these. (Path B inherits 1–5 in spirit; §10 maps them onto the
Buttons config.)

## 4. Where the code goes (Path A)

```
src/coda/apps/reporting/
  urls.py              # path "stats/fundingrequests/export/<str:dimension_id>/"
  views/export.py      # csv_export(request, dimension_id)
  views/page.py        # _sections() gains export_url on DimensionSection
  templates/reporting/ # download button per section table
```

The pure layer gains nothing: `group_by(top_n=None)` and the comparison fact fetch already
exist. The only new logic is label-joining the two groupings and serializing.

## 5. Data flow (Path A)

```
GET /stats/fundingrequests/export/<dimension_id>/?<page filter params>
  -> FundingRequestListFilterForm(request.GET, contracts=…, labels=Label.used_labels(),
       vocabularies=GlobalPreferences.preloaded(), include_labels_widget=True)
     + is_valid()                          # identical construction to the page (page.py)
  -> factcache.facts_for(GET, currency, build_facts)      # cache hit after a page render
  -> [compare on] resolve comparison_period via the shared helper (§5.1)
     factcache.facts_for(..., comparison_period=period)   # second cached fact set
  -> aggregation.group_by(facts, dimension, top_n=None)
  -> [compare on] group_by(comparison_facts, dimension, top_n=None)
  -> label-join rows -> polars DataFrame -> HttpResponse
```

### 5.1 Comparison-period resolution (extracted)

The resolution currently lives inline in `reporting_context` (`page.py`). Extract it into a
module-level helper so the page and the export cannot drift — same rules: explicit
`compare_range` wins over `prior_window()`; one-sided or invalid ranges disable the
comparison rather than fail. The helper returns `(period, error)` and **does not touch the
form widgets**: the one-sided-sentinel case also calls `DateRangeWidget.mark_invalid()`
and produces the band's `comparison_error` string on the page — the caller (page or
export) owns that side effect. The export treats `error is not None` as compare-off and
emits current-period columns only, matching the page's `compare=False` rendering.

## 6. CSV shape (both paths; Path B realizes it via the Buttons config)

One table per file; no `dimension` column (the filename names it). The header derives from
the dimension's measures (`dimension.measures()`), with one deliberate exception: the
money column is always **`amount`**, whatever it means per dimension (settled Q5 — "it's
all monetary amount in the end"; the spend-vs-funded-by distinction lives in the page's
column headers only):

```
label;currency;publications;amount;comparison_publications;comparison_amount   # both measures
label;publications;comparison_publications                                     # funder (no money)
label;currency;amount;comparison_amount                                        # cost type (no count)
```

`funding_source`'s `amount` is *funded by*, not spend — accepted ambiguity of the uniform
name; the display labels ("spend incl. tax" / "funded by incl. tax") stay on the page.

- A dedicated **`currency` column** follows the `label` column when the dimension has a
  money measure (funder, no money, has no empty currency column). It holds the home
  currency's code — `EUR` — on every row, comparison cells included: one page-wide
  currency per ADR-0003, so the code is file-level, not per period. `amount` cells are
  bare decimals in that currency; amounts without an exchange rate are excluded exactly
  as on the page, and a blank comparison cell (no prior counterpart) stays blank.
- Comparison columns present when compare is on, absent when it is off (the file then
  describes only the current period).
- Blank comparison cells for rows absent from the prior period. No "new" marker, no deltas.
- No totals row: the table's `<tfoot>` total (or the non-additive note where totals are
  forbidden) stays on the page — the export is raw rows only.
- Rows join by label, identical to `_sections()`' comparison join. A label whose
  composition changed between periods joins anyway — same semantics as the table.
- Row order: the grouping's rank order (money first, then count), the table's order.
- UNKNOWN/UNASSIGNED rows are exported (they are the data-quality signal), labelled as such
  in `label` exactly as on the page. The non-additive caveat (ADR-0007) is deliberately
  *not* carried into the file: the export is raw data, the note stays on the page.
- Label cells are written verbatim, like every other export in this project. A label
  starting with `=`, `+`, `-` or `@` can read as a formula when the file opens in a
  spreadsheet. Accepted and documented here, not neutralized: neutralizing would alter
  the data.

## 7. View contract (Path A)

- Unknown `dimension_id` → 404 (`dimensions.by_id`).
- Date-error behavior mirrors the page, not a CSV body with a sentence in it: invalid date
  params → HTTP 400 with the form's error text (the region skips the pipeline on date
  errors; the export has no region to show an inline error in). Bare-GET with no dates at
  all (hand-typed/bookmarked URL) → same 400; the page redirects to the default period, an
  export with a silently different period than the user saw would be worse.
- Filter params ride the query string. The prune set is **not** `list_view_url`'s:
  `DISPLAY_STATE_PARAMS` includes the compare dates, so pruning "the way the list URL
  prunes" would strip the comparison window. The export keeps:
  - all filter params (unchanged),
  - `compare` — the compare toggle. The page's URL can carry stale compare dates while the
    switch is off (htmx push-url history), so date presence alone is not "compare is on";
    the export gates on `compare == "1"` exactly as the page does. It is excluded from the
    facts cache key anyway, so keeping it costs nothing;
  - `compare_start_date` / `compare_end_date` — these define the comparison window;
  - dropped: `tab`, `page`, `resolution`.

  `DimensionSection.export_url` is built in `_sections()` from `request.GET` — `request`
  must be plumbed in (it currently receives `report`, `links`, `comparison` only; the GET
  params live on `DrilldownLinks.request`), or a small builder beside
  `drilldown.list_view_url` takes `request.GET` + dimension id.

## 8. Template (Path A — as shipped)

The export lives **inside the expandable table section** (user request): a plain text link
(`<small>`-wrapped `<a href="{{ section.export_url }}" download>Export table as CSV</a>` —
no button chrome), right-aligned with the house `flex justify-end` utility, directly below
the table in `templates/reporting/partials/reporting_groups.html`'s `<details
class="statistics-exact">`, **outside the `<summary>`** (a control inside the summary
would toggle the details on click). The `download` attribute makes it a file download.
The link itself needs no JS; the fold disclosure (§9) has its own
small delegated handler.

## 9. Path A: expanding the "Other" row on the page (as shipped)

The table gains a disclosure under its "Other" row revealing the folded values — the same
complete set the CSV exports. This makes the shared row source structural, not a refactor
nicety:

- The page computes the unbounded grouping per dimension (`group_by(top_n=None)`) and
  slices it: visible = first `DEFAULT_TOP_N`, folded = the rest. The chart keeps its own
  bounded grouping (`charts.report` untouched) — the table becomes a superset of the
  chart's row set, a deliberate relaxation of the "table and charts share exactly its row
  set" contract in `aggregation.py`; both still derive from the same fact set, so they
  cannot disagree about values, only about visibility.
- **Mechanism (shipped):** a second `<tbody hidden id="folded-<dimension_id>">` after the
  Other row — a nested `<details>` cannot wrap `<tr>`s, and the table already sits inside
  one. Expanding **replaces** the Other row rather than augmenting the table (user
  request): a document-delegated handler in `reporting.js` (same pattern as the column
  sorting, so htmx-swapped tables work without re-init; a native button covers
  Enter/Space) moves the tail `<tr>`s into the main tbody in front of the Other row, which
  then hides itself — the unveiled values are ordinary rows that `sortRows()` (which sorts
  only `tBodies[0]`) orders with the rest, and the fold aggregate yields to them.
  Collapsing moves the tail back into the hidden tbody, restores the Other row, and
  returns the table to the server's rank order (each row keeps its server index from the
  expand step, so any client-side sort is undone). The expand control ("Show N more") is a
  plain text link — `<a class="statistics-fold-toggle" tabindex="0" aria-expanded="false">`,
  Pico's base `a` look, the same as the export link; deliberately no `role="button"`
  (Pico paints role-button anchors as filled form buttons) and no `undecorated` class —
  in the Other row's label cell, so it disappears with
  the row; the collapse control ("Show top values only", same styling) is a server-rendered
  `hidden` tfoot row — never a sorted data row — shown only while expanded; both controls
  mirror `aria-expanded`. An href-less anchor cannot navigate but is also not natively
  key-activatable, so `reporting.js` mirrors the sortable headers' delegated Enter/Space
  handling for these controls. No GET param, no `DISPLAY_STATE_PARAMS` change, no round
  trip — the full set is already in the DOM.
- Folded rows are real values: they carry drilldown links and comparison columns like the
  visible ones (shared `reporting_value_row.html` partial). "Other" itself keeps no link
  (unchanged — the shared form cannot express the set).
- `value_count` ("Exact values (N rows)") becomes the full distinct count; the data is
  present regardless of expansion state.
- `group_by` runs bounded (figure), unbounded (table) and bounded again (the Other fold)
  per dimension over the cached fact set — negligible; no refactor of `charts` internals.

The CSV export (§6) serializes exactly the unbounded rows — the expansion's content,
minus links. One row builder, three consumers: visible table, expansion, CSV.

### 9.1 Deliberate page-render deltas from the unbounded join (review-recorded)

Three visible-row behaviors change against the pre-expansion page; all spec-consistent,
pinned by tests, listed so nobody mistakes them for regressions:

1. Visible rows join the comparison's *unbounded* grouping, so a row whose prior
   counterpart ranked outside the comparison's top-10 now shows a real delta badge
   instead of the old "new" badge (the old badge was wrong there).
2. `unattributed` sums over the full unbounded rows — previously it missed an Unknown row
   folded beyond the top-10. Strictly more accurate.
3. The Other row comes from the bounded grouping's own fold (`group_by(top_n=10)`) rather
   than re-folding the unbounded grouping in the view; provably equivalent (same rank
   function, same label set), keeps the fold logic in one place, costs one more
   `group_by` over the cached fact set. Commented in `page.py`.

## 10. Path B — alternative: DataTables renders the tables, Buttons exports the CSV

DataTables 2 standalone (jQuery-free core) takes over the section tables; the Buttons
extension's CSV button replaces the server export. `serverSide: false` (the default,
client-side mode) is a hard requirement: server-side processing would move paging/search
into a new Ajax endpoint, contradict ADR-0004's in-memory aggregation, and — decisive —
the client would then hold only one page of rows, so the CSV button could no longer export
the complete set and the server export endpoint would be needed anyway.

### 10.0 Considered and rejected: simple-datatables

Evaluated against the same requirements (source read, v10.3.0, `../simple-datatables`).
Viable library — vanilla, single module, smaller than DT core+Buttons, `exportCSV` exports
the complete set regardless of paging/search (`selectedRows = dt.data.data`), `;`/
filename/selection options, `data-content`/`data-order` orthogonal read attributes — but
rejected on the export model:

- Export text comes from `cellToText(cell)` = `cell.text ?? cellToText(cell.data)`
  (`helpers.ts`); there is **no attribute-level raw source for export**. DataTables reads
  `data-sort` for both sorting and export while the cell keeps its rich markup;
  simple-datatables cannot.
- Consequence for our cells: type `html` (rich display preserved) → the CSV would carry
  the display text — formatted amounts, `+25%`/`new` badges, share spans — violating §6.
  `data-content="<raw>"` (raw export) → the rich display is discarded at read time and
  re-rendered as a plain text node; recovering it means re-implementing the template's
  cell formatting (floatformat, €, badges, share bars) in a `columns.render` callback.
  Either the export degrades or the formatting logic is duplicated in JS.
- Secondary: **LGPL-3.0** (vs DT's MIT) — workable for a vendored asset but a compliance
  conversation this project doesn't need; no `bom` option (custom wrapper needed); the
  demo's `encodeURI`-based download truncates on `#` in labels (would need our own Blob
  download); no column-visibility/pageLength UI.

The tables' combination — rich cells (formatted money, badges, notes) with a raw-values
export — is exactly what its export model handles worst and DT's orthogonal data handles
directly.

### 10.1 Vendoring

```
src/coda/apps/static/js/vendor/dataTables.min.js           # DT 2 core
src/coda/apps/static/js/vendor/dataTables.buttons.min.js   # Buttons core (no JSZip/pdfmake needed for CSV)
src/coda/apps/static/css/vendor/dataTables.buttons.min.css
```

MIT-licensed; script/link tags like the plotly precedent, with the same SHA-256 pin test
the vendored `plotly.min.js` has.

### 10.2 What is deleted from Path A

§4 (export view), §5 (data flow), §7 (view contract), §8 (template button),
`export_url` plumbing in `_sections()`. §9's expansion disappears — the full table is
always there, paged by DT.

### 10.3 What is added

- **Init** in `reporting.js`'s orbit, one per section table:

  ```js
  new DataTable(table, {
      layout: { topStart: { buttons: [{
          extend: 'csv',
          text: 'CSV',
          bom: true,                                  // = the project's utf-8-sig
          fieldSeparator: ';',
          filename: dimensionId,
          exportOptions: { modifier: { search: 'none' } },   // complete set, not the page
      }]},
  });
  ```

  Rows come from the server-rendered HTML (DT reads the `<table>`), or via the `data`
  option fed from `json_script` — the same pattern the page uses for plotly figures — if
  the ~300 KB venues-tab payload (journal 1074 + publisher 214 rows) proves heavy.
- **htmx re-init**: every region swap must destroy/re-init the tables
  (`htmx:afterSwap` hook). This hook is load-bearing — the page re-renders on every filter
  edit and tab switch — and DT's page/search state resets across swaps unless persisted.
- **Orthogonal export data** (the raw-values contract, in JS instead of a tested function):
  - raw decimals from the existing `data-sort` attributes (`reporting_groups.html:62`
    already carries `data-sort="{{ row.amount }}"` / `{{ row.publications }}`);
  - **new** `data-comparison-amount` / `data-comparison-publications` attributes — the raw
    comparison values are *not* in the DOM today (the table shows only delta badges and
    "new" markers), so the template must expose them;
  - `columns` config selecting label, publications, amount, comparison columns — and
    excluding the delta badges, share spans, and the non-additive note.
- **Styling alignment**: the project's tables are Pico-styled; DT ships its own default
  CSS (no Pico integration). Expect a small CSS pass, or the button gets Pico's
  `button secondary` classes via `className`.

### 10.4 Path B risks

- Export correctness depends on the JS contract (attributes present, `columns` config
  right); no *unit-level* net — coverage comes from the Playwright suite (§11).
- `test_page.py`'s HTML assertions survive, and the export **is** assertable in-repo — the
  reporting page has a Playwright suite (`test_reporting_ui.py`), so `page.expect_download`
  can pin the CSV's bytes. The difference from Path A is test *level*: the thing under
  test is the JS contract (attributes present, `columns` config right), verified
  end-to-end in a browser, slower and coarser than a pytest call on a pure function. A
  template change that drops a `data-*` attribute still fails loudly in CI — via a UI
  test, not a unit test.
- Two vendored libs; plotly-sized risk is small (~100 KB vs 4.6 MB), but the re-init hook
  is a real integration surface this page exercises heavily.

## 11. Testing (`tests/reporting/`)

Path A (full list):

- Full-row export vs. the page's top-10: same filters, export strictly superset, no
  "Other" row, row count equals the unbounded grouping's.
- Table expansion: folded rows render inside the disclosure with correct publications,
  amount, comparison values and drilldown links; the visible set plus folded rows equals
  the export's rows; chart rows unchanged (top-10 + Other).
- Comparison values: raw prior-period numbers joined by label; compare off → columns
  absent; row missing from the prior period → blank cells.
- Cache reuse: export immediately after a page render with the same filters returns
  identical numbers without a second pipeline run (pins the §5 performance claim; note
  `conftest.py`'s autouse `clear_fact_cache`).
- URL pruning: `export_url` drops `tab`/`page`/`resolution`, keeps all filter params,
  `compare`, `compare_start_date`, `compare_end_date` (pins §7's prune set).
- Per-dimension headers: the money column is `amount` on every dimension —
  `label;publications;amount;comparison_publications;comparison_amount` for a both-measures
  dimension, `label;amount;comparison_amount` for cost type, `label;publications;…` for
  funder (pins §6's header rule).
- Repeated-dimension semantics: one request under two values → both rows count it.
- UNKNOWN/UNASSIGNED rows present; zero-money suppression for cost type preserved.
- View: unknown dimension → 404; invalid dates → 400 with the form error; compare-on
  semantics gated on `compare=1` with `compare_start_date`/`compare_end_date` respected.
- CSV bytes: `;` separator, `utf-8-sig` BOM, header row exact.

Path B: the server-side list shrinks to the shared row source (unbounded grouping +
label join, if extracted) and the template's new `data-*` attributes; export bytes are
assertable via `page.expect_download` in the existing Playwright suite — same §11 cases,
just exercised at browser level (`uitests` script) instead of pytest.

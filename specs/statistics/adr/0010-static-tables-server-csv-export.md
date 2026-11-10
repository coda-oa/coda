# Statistics tables are static HTML with a server-side CSV export, not a JavaScript grid

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

The statistics page's exact-value tables render as server-built static HTML, the complete set
beyond the visible top 10 stays in a client-side disclosure under the "Other" row, and the CSV
export is a server endpoint over the same in-memory grouping (see `specs/statistics/csv-export.md`).
A JavaScript table grid — DataTables 2 or simple-datatables — was evaluated and rejected, despite
the page already vendoring a far larger JS asset (plotly, 4.6 MB).

The evaluation lives in the plan's §2, §10 and §10.0; the decision rests on three points:

- **The requirement is availability, not interactivity.** The full value set must be *visible*
  (disclosure) and *downloadable* (CSV). Nothing requires searching or sorting the long tail —
  measured at 1074 distinct journals, 707 of them with a single request — which is the only thing
  a grid buys that the disclosure does not.
- **The export contract stays testable at unit level.** The CSV is a pure function of the cached
  fact sets, asserted byte-exact in pytest. Grid-based export moves the contract into JS
  configuration and DOM attributes, verifiable only at browser level.
- **No second framework.** The page's interactivity is htmx plus a single vendored plotly bundle;
  a grid adds a destroy/re-init hook on every htmx region swap — and this page swaps on every
  filter edit — plus, in simple-datatables' case, an export model without an orthogonal raw-value
  source, which would force display-formatted CSV values or duplicated formatting logic in JS
  (LGPL-3.0 besides).

## Consequences

The statistics feature vendors no grid library, and a future table feature starts from static
HTML + disclosure rather than "which grid do we add". If tail search is ever actually demanded,
DataTables 2 standalone is the recorded fallback (plan §10); the shared data layer — unbounded
grouping plus comparison label join — is built so that switching does not redo it. The CSV
remains a server artifact with a stable, uniform header contract (`amount` as the money column on
every dimension), independent of any table rendering.

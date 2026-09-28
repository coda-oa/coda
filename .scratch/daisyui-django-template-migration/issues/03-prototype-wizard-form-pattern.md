# Prototype a DaisyUI pattern for the funding-request wizard

Status: resolved
Type: prototype
Blocked by: 02

## Question

What reusable DaisyUI presentation should CODA use for complex Django forms? Create a throwaway visual prototype based on the funding-request publication/author step, including a normal field, validation error, dynamic formset row/HTMX replacement, and the existing search-select web component. Show light and dark states using the approximate current blue/neutral palette. Keep the current form names/IDs, ARIA and HTMX contracts represented; link the artifact from this ticket and get the user's reaction on visual hierarchy, density, and component treatment. Do not change production templates.

## Comments

Prototype preview: [Open the funding-request form variants](http://127.0.0.1:8765/.scratch/daisyui-django-template-migration/prototypes/funding-request-form-pattern/index.html?variant=ledger). Switch layouts with the floating arrows or `←`/`→`: `ledger` (dense table), `records` (stacked author records), and `split` (side-by-side authors and metadata). Use the theme toggle for light/dark.

The source is committed on branch `prototype/funding-request-form-pattern` at `e1f7b134` (`.scratch/daisyui-django-template-migration/prototypes/funding-request-form-pattern/index.html`). The daisyUI CDN is preview-only; production CSS remains locally compiled. HTMX attributes and form identifiers are represented, but requests and form submissions are intentionally inert.

## Answer

The user selected **A · Ledger** as the baseline: compact, table-first author and link rows with clear columns. This resolves the layout/density direction for the shared form pattern. Preserve the existing field names/IDs, HTMX targets/swaps, validation semantics, light/dark behavior, and approximate CODA palette; no further color preference was stated.
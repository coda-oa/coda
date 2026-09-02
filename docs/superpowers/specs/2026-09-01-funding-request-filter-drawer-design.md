# Funding Request List: Responsive Filter Drawer

**Date:** 2026-09-01
**Status:** Approved
**Supersedes:** the "always docked" assumption in `2026-09-01-funding-request-filter-sidebar-design.md` for viewports below 1400px.

## Problem

The funding request list page (`/fundingrequests/list/`) has a 250px filter sidebar docked on the right. On a 13" laptop (~1280px viewport), the expanded left nav (~28ch) plus the docked sidebar leaves the data-heavy list only ~600–700px wide. CODA is not expected to be used on phones, but 13" laptops are.

## Goal

Maximize list width on narrow screens: the list wins, and filters get tucked away and pulled out when needed — **without losing the live-filtering behavior** (filters apply live via HTMX; no Search button).

## Decisions (from brainstorming)

- **List wins** on narrow screens (over keeping filters always visible).
- **Pull-out mechanism: overlay drawer without scrim** — the list stays visible on the left and updates live while filters are adjusted in the drawer. Rejected: inline collapse (list width jumps), modal dialog (list blocked; each tweak is open → adjust → close → verify).
- **Breakpoint: 1400px** — docked sidebar at ≥1400px, drawer mode below.
- **Drawer is closed by default on every load** — the toolbar "Filters (n)" button carries the active count. No state persistence.
- **Mechanism: CSS media query + tiny vanilla JS class toggle.** One DOM node serves both modes; no form duplication, no view/HTMX changes.

## Behavior

### ≥1400px

Unchanged: 250px sidebar docked on the right, sticky, `max-height: calc(100vh - 2rem)` with inner scroll. No toggle button, no close button.

### <1400px (drawer mode)

- The same `<aside class="filter-sidebar">` node is restyled as a fixed right-edge drawer: full viewport height (`top: 0; right: 0; bottom: 0`), own scroll, same 250px width, page background token, shadow on the left edge, `z-index` above the list.
- Translated fully off-canvas by default (`transform: translateX(100%)`); opening applies `transform: translateX(0)` with a 200ms ease transition.
- **Open:** "Filters" button in the toolbar (shows active count badge when `filter_count > 0`, plain "Filters" when 0).
- **Close:** × button in the drawer header, `Esc` key, or the toolbar button again.
- **No scrim** — the list remains visible and interactive; HTMX live filtering works while the drawer is open.
- **Always closed on load**; the open/closed state is not persisted anywhere.
- **Resizing across the threshold** restyles the same node; the open/closed class is scoped inside the media query so it cannot leak between modes.

## Architecture

### Templates

- **New partial** `src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html`:
  - `<aside class="filter-sidebar">` wrapper
  - `<form method="get" id="filter-sidebar-form">`
  - `{% include "fundingrequests/fundingrequest_filter_sidebar.html" %}`
- `fundingrequest_list.html` includes the drawer partial in place of the inline `<aside>` it currently contains. All drawer-specific markup lives in the partial; the list page keeps only the layout.
- `fundingrequest_filter_toolbar.html` gains a toggle button:
  - `<button type="button" id="filter-drawer-toggle">` with the label "Filters" and a count badge when `filter_count > 0` (context already available)
  - `type="button"` so it never submits the toolbar form
- The drawer header — `partials/fundingrequest_filter_header.html` (`#filter-sidebar-header`, the OOB swap target, included at the top of the sidebar) — gains a × close button, visible only in drawer mode.

### CSS (`fundingrequests.css`)

- All ≥1400px rules unchanged.
- One `@media (max-width: 1399.98px)` block:
  - `.filter-sidebar` → `position: fixed; top: 0; right: 0; bottom: 0; transform: translateX(100%); transition: transform 0.2s ease;` full-height scroll (`max-height: none`), background token, left-edge `box-shadow`, `z-index` above the list
  - `.filter-drawer-open .filter-sidebar` → `transform: translateX(0)`
  - `#filter-drawer-toggle` → visible (inline-flex)
  - × close button → visible
- Outside the media query, `#filter-drawer-toggle` and the × button are `display: none`.

### JavaScript (new `src/coda/apps/static/js/filter-drawer.js`)

- ~20 lines of vanilla JS, loaded like the existing `static/js` files:
  - toggle `.filter-drawer-open` on the `.filter-layout` element when `#filter-drawer-toggle` is clicked
  - remove the class when the × button or `Esc` is pressed (Esc only acts while open)
- **Event delegation is required** for the × close button: the drawer header (including ×) is the HTMX out-of-band swap target, so its DOM is replaced after every filter change. Listeners must live on a stable ancestor (e.g. the `<aside>` or `.filter-layout`), not on the × element itself.
- The toolbar toggle is a disclosure: `aria-controls="filter-sidebar"` and `aria-expanded` (kept in sync by the JS). The `<aside>` carries `id="filter-sidebar"`.
- No framework, no Django or HTMX changes.

### What does not change

- The view (`listview.py`), `filter_count()`, URL, all query-param names, the HTMX region and its triggers (`change from:#filter-sidebar-form`, etc.) — one DOM node, same ids, so both modes work off the existing wiring.
- The docked sidebar appearance and behavior at ≥1400px.

## Testing

- **No new automated tests** (agreed: the candidates were markup-presence checks, not business use cases).
- The 14 existing tests in `tests/fundingrequests/test_fundingrequest_list_view.py` must pass unchanged (same ids and forms).
- Manual verification checklist:
  - Resize 1450px → 1350px: sidebar leaves the flow, list widens, toggle button appears
  - Toggle opens/closes with the 200ms slide; × and Esc close it
  - Live filtering visible while the drawer is open; count badge follows
  - Toolbar search/sort still work while the drawer is open
  - ≥1400px: docked sidebar, no toggle, sticky behavior unchanged
  - Dark mode: drawer background/border/shadow tokens
  - Reload with active filter params: drawer closed, "Filters (n)" badge shows the count

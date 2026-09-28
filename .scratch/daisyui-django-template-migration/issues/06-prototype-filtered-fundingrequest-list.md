# Prototype DaisyUI filters for the funding-request list

Status: resolved
Type: prototype
Blocked by: 05

## Question

How should CODA style its data-heavy funding-request list and filters with daisyUI? Create a throwaway prototype based on `fundingrequests/fundingrequest_list.html` and the shared filter layout: the 280px sticky desktop sidebar, narrow-screen drawer/backdrop, search/sort/filter-count toolbar, label pills, active-filter chips, and HTMX-updated request list. Show a populated result list, active filters, a no-results state, multi-select, segmented publication type, and date validation. Preserve form names/IDs, `#filter-sidebar-form`, `#filter-toolbar-form`, `#fundingrequest-list`, HTMX includes/triggers/targets, and drawer ARIA/focus semantics. Compare three structurally distinct presentations while retaining the existing page and interaction structure; show light/dark and responsive states. Do not change production templates; prototype-only server actions may remain inert.

## Comments

Preview: [Funding-request filter variants](http://127.0.0.1:8766/.scratch/daisyui-django-template-migration/prototypes/funding-request-list/index.html?variant=faceted). Switch with the floating bar or `?variant=faceted`, `?variant=ledger`, and `?variant=queue`; both themes and a no-results state are available. After your feedback, label pills now occupy a wrapping row under search, and queue entries have a light surface, thin border, and status rail rather than a heavy card. The drawer and search-select use CODA's existing JavaScript; HTMX requests remain inert.

Source: branch `prototype/fundingrequest-filter-list`, commit `185e2a48`, `.scratch/daisyui-django-template-migration/prototypes/funding-request-list/index.html`.

## Answer

Use **C · Triage queue** for the funding-request list. Put label filters on a separate wrapping row directly below search, since there may be many; give each request a subtle surface, thin boundary, and status rail—more separation than plain dividers, without a heavy card. Keep the existing right-side sidebar/drawer, form controls, and HTMX contracts.
# Prototype DaisyUI patterns for reference-data registries

Status: resolved
Assignee: @SvenMarcus
Type: prototype
Blocked by: 12

## Question

How should CODA present its reference-data registries after the DaisyUI cutover? Create a throwaway UI prototype for publishers, journals, creditors, funding sources, funders, and labels. Compare two structurally different directory/detail/edit hierarchies using representative records and the relationships, identifiers, hierarchy, and lifecycle states supported by each entity. Show search and selection where existing workflows provide them, plus light/dark and responsive states. Preserve existing field names/IDs, ARIA semantics, and HTMX response roots/targets/swaps; keep actions inert and do not change production templates.

## Comments

Initial preview (superseded after user feedback): A · Unified catalog and B · Registry workspaces. Current preview links are in the revision below.

The prototype shows blocklist, archive/restore, identifier, journal/publisher, invoice, funding-request, and label color/attachment states where supported. Existing field names/IDs and HTMX targets/swaps are represented, but sample data and actions are inert. Production templates are untouched.

Initial browser smoke (before feedback) covered both original directory patterns, all six registry categories, journal/funder/creditor/funding-source detail/edit paths, label edit/delete and attach/detach preview, and a 390px viewport; no console errors. [Source file](../prototypes/reference-data-registries/index.html).

First follow-up revision (superseded by the team-boundary clarification): A and B grouped catalogs without a cross-domain record table.

Initial three-group previews (A · Grouped catalogs and B · Domain portals) were superseded by the team-separated revision below.

First follow-up smoke, before the team-boundary refinement, covered the grouped overview, catalog-scoped search, funder/creditor archive filtering, and a 390px viewport; no console errors. [Source file](../prototypes/reference-data-registries/index.html).

Team-boundary clarification: Funding requests and publishing share one team; Finance is the separate team. This sidebar-navigation revision keeps that boundary while restoring CODA’s existing page groups.

The Funding requests team owns publishers, journals, funding organizations, and request labels. Labels stay with this team because `FundingRequest.labels` is a many-to-many relation to `fundingrequests.Label`.

The Invoices page uses inert sample rows from the existing invoice workflow to show where finance navigation leads; registry actions remain simulated.

Current navigation follows CODA’s sidebar hierarchy: Request Center → Funding Requests/Funders; Journals & Publishers → Journals/Publishers/Blocklist; Finances → Invoices/Creditors/Funding Sources. Request Labels remain inside Funding Requests, not a new sidebar item. B is the preferred default.

Preview B · Sidebar + page cards: [open B](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=workspaces&page=request-center).

Preview A · Sidebar + category rail: [open A](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=unified&page=request-center).

Earlier team-portal smoke (before the sidebar refactor) covered team boundaries, archive filtering, detail/edit context, and the 390px viewport; no console errors.

Browser smoke after the sidebar revision covered Request Center → Funding Requests/Funders, Journals & Publishers → Journals/Publishers/Blocklist, Finances → Invoices/Creditors/Funding Sources, Request Labels from Funding Requests, scoped search/archive filtering, and A/B route preservation. At 390px the sidebar opened, navigated, and closed without horizontal overflow; no console errors. [Source file](../prototypes/reference-data-registries/index.html). Ticket remains open for feedback.

Latest revision after scope clarification: Funding Requests and Invoices pages and their workflow/sample data, plus Blocklist navigation/actions, are excluded. Request Center retains Funders and Request Labels; Journals & Publishers retains Journals and Publishers; Finances retains Creditors and Funding Sources. B remains the default, and both variants use A's sectioned detail hierarchy. Catalog titles, editor labels, and singular/plural counts use entity-specific names.

Preview B · Sidebar + page cards: [open B](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=workspaces&page=request-center).

Preview A · Sidebar + category rail: [open A](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=unified&page=request-center).

Desktop smoke covered in-scope directories, details/edit paths, scope exclusions, search empty states, and both layouts; 390px smoke covered mobile navigation, detail, and dark theme. No browser or console errors. [Source file](../prototypes/reference-data-registries/index.html). Ticket remains open for human review.

Follow-up to linked-record feedback: Creditor details now list their invoices; Funding Source details list invoices with the funding-source allocation. Funding Organization and Journal details now list their related Funding Requests. Publisher references appear in B's directory column and A's selected-publisher preview; no new Publisher detail route was invented because CODA has no production Publisher detail view. Funding Requests and Invoices pages/workflows remain excluded; these are static sample references only.

Preview B · Creditor invoices: [open B](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=workspaces&page=creditors).

Preview A · Publisher funding requests: [open A](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=unified&page=publishers).

Browser smoke covered active/archived creditors and funders, funding-source invoice allocations, both Journals, Publisher references in both layouts, and 390px detail/list previews with no horizontal page overflow. No browser or console errors. [Source file](../prototypes/reference-data-registries/index.html). Ticket remains open for human review.

Publisher-detail follow-up: added sectioned detail pages for both sample Publishers. View actions in A and B open the same hierarchy, showing linked Journals and Funding Requests. This is prototype-only despite the absence of a production Publisher detail route; production templates remain untouched.

Preview B · Publisher directory: [open B](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=workspaces&page=publishers).

Preview A · Publisher details and related-request preview: [open A](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/reference-data-registries/index.html?variant=unified&page=publishers).

Desktop and 390px browser smoke verified both Publisher details, linked references, and layout switching; no overflow, browser errors, or console errors. [Source file](../prototypes/reference-data-registries/index.html). At this point, the ticket remained open for human review.

Resolution comment (human approved): B · Sidebar + page cards remains the preferred default, with A's sectioned detail hierarchy shared across layouts. The accepted scope keeps Funders and Request Labels in Request Center, Journals and Publishers in Journals & Publishers, and Creditors and Funding Sources in Finances. Creditor/Funding Source details reference invoices; Funding Organization, Journal, and Publisher details reference Funding Requests. Publisher detail pages are prototype-only. Funding Requests and Invoices pages/workflows and Blocklist navigation/actions remain excluded; all sample data/actions are inert and production templates are untouched.

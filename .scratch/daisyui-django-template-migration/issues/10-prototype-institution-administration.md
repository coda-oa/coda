# Prototype DaisyUI institution administration workflows

Status: resolved
Assignee: @SvenMarcus
Type: prototype
Blocked by: 09

## Question

How should the institution directory and management workflows present hierarchy, affiliation availability, relationships, and lifecycle actions after the DaisyUI cutover? Create a throwaway prototype based on `institutions/institution_list.html`, `institution_list_header_bar.html`, `institution_list_item.html`, `institution_detail.html`, `institution_form.html`, `institution_import.html`, `institution_restore_modal.html`, and `institution_successor_modal.html`. Compare two directory/detail hierarchies using active and archived institutions, parent/child relationships, a virtual institution, and related funding-request, invoice, and identifier records. Include create/edit and CSV import entry points, archive-to-successor states (including a home institution and children), and restore states (including archived children and parent selection). Show light/dark and responsive states. Preserve form names/IDs, ARIA semantics, response roots/selectors, and existing HTMX targets/swaps for affiliation toggles, archive/delete/restore actions, and modal submissions. Actions may remain inert; do not change production templates.

## Comments

Preview: [Tree search example](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/institution-administration/index.html?variant=tree&query=Digital%20Scholarship). The sample query shows one matching child beneath a nonmatching parent.

The user prefers A's tree directory and asked to remove the Directory / Institution detail switch. The tree variant now uses B's full, sectioned detail page; **Open full profile** enters it and **Back to tree** returns. B's register list remains available for comparison with the same detail page.

Search behavior shown: keep name matches in place, retain their ancestor chain as muted `Context` rows, hide unmatched siblings/branches, and count only matching institutions. Select the first match if the current selection is outside the result set. Archived ancestors can appear as `Archived context` when archived records are included; active children cannot have archived parents. The current repository search returns name matches only. This prototype simulates filtering client-side to review the tree projection; production filtering will be server-side through HTMX.

Forms and HTMX actions remain inert; production templates are untouched. Browser smoke covered the combined tree/sectioned-detail flow, search context, archive filtering, linked records, lifecycle dialogs, form/import identifiers, and a 390px viewport. [Source file](../prototypes/institution-administration/index.html).

## Answer

Use A's tree directory with B's sectioned full detail. Remove the Directory / Institution detail switch; **Open full profile** enters the record and **Back to tree** returns. Search by institution name, show matches in place with the necessary ancestor chain as muted `Context` rows, count matches only, and hide unmatched branches/siblings. Select the first match if the current selection is outside the results. Archived ancestors may be context for matching archived descendants when archived records are included; active children cannot have archived parents. Production filtering remains server-side via HTMX; client-side filtering is prototype-only.

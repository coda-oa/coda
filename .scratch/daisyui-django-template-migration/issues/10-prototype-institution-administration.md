# Prototype DaisyUI institution administration workflows

Status: open
Type: prototype
Blocked by: 09

## Question

How should the institution directory and management workflows present hierarchy, affiliation availability, relationships, and lifecycle actions after the DaisyUI cutover? Create a throwaway prototype based on `institutions/institution_list.html`, `institution_list_header_bar.html`, `institution_list_item.html`, `institution_detail.html`, `institution_form.html`, `institution_import.html`, `institution_restore_modal.html`, and `institution_successor_modal.html`. Compare two directory/detail hierarchies using active and archived institutions, parent/child relationships, a virtual institution, and related funding-request, invoice, and identifier records. Include create/edit and CSV import entry points, archive-to-successor states (including a home institution and children), and restore states (including archived children and parent selection). Show light/dark and responsive states. Preserve form names/IDs, ARIA semantics, response roots/selectors, and existing HTMX targets/swaps for affiliation toggles, archive/delete/restore actions, and modal submissions. Actions may remain inert; do not change production templates.
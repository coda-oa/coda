# Prototype a DaisyUI invoice-position editor

Status: resolved
Type: prototype
Blocked by: 07

## Question

How should the invoice position editor present cost, tax, funding assignments, and totals after the DaisyUI cutover? Create a throwaway prototype based on `invoice_positions.html`, `position_base.html`, `position_generic_partial.html`, `position_funding_assignments.html`, and `position_summary.html`. Compare three distinct hierarchies using publication, contract, and free-position examples; include the implicit, single-assignment, and split-funding states plus an invalid/unassigned-cost warning. Preserve existing open `<details>` sections, field names/IDs, position roots, and HTMX targets/swaps for add/remove, cost-type changes, funding splits, and `#positions-summary` recalculation. Show light/dark and responsive states. Do not change production templates; backend actions may remain inert.

## Comments

Prototype preview: [Invoice position layouts](http://127.0.0.1:8768/.scratch/daisyui-django-template-migration/prototypes/invoice-positions/index.html?variant=sections). Switch using the floating bar or `?variant=ledger`, `?variant=sections`, and `?variant=allocation`; light/dark themes are available. The selected B · Expanded sections layout keeps position-specific details, core fields, and funding assignments grouped, with Amount, Tax Rate, and Cost Type aligned on one desktop row; fields stack at ≤460px to prevent horizontal overflow. Funding assignment rows reserve an action column so Source Type, Funding Source, and split Amount stay aligned across rows. Includes publication, contract, and free positions; implicit, single, and split funding; and an invalid/unassigned-cost warning. Field IDs and HTMX targets are shown; actions are inert.

Source: branch `prototype/invoice-position-editor`, commit `07dfa7ec`, `.scratch/daisyui-django-template-migration/prototypes/invoice-positions/index.html`. Production templates are untouched; DaisyUI CDN is preview-only.

## Answer

Choose **B · Expanded sections**. Keep position-specific details, core fields, and funding assignments in distinct vertical groups; align Cost Type, Amount, and Tax Rate on one desktop row. Within funding assignments, keep Source Type, Funding Source, and split Amount in consistent columns across rows by reserving the action column. At widths ≤460px, stack the fields to prevent horizontal overflow. Preserve the existing open-details structure, field names/IDs, position roots, and HTMX targets/swaps.
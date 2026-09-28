# Prototype DaisyUI contract administration workflows

Status: resolved
Assignee: @SvenMarcus
Type: prototype
Blocked by: 09

## Question

How should the contract directory and management screens present contract status, billing mode, identifiers, and linked publishers/journals after the DaisyUI cutover? Create a throwaway prototype based on `contracts/contract_create.html`, `contract_detail.html`, `contract_list_item.html`, `contract_active_status.html`, `contract_search_add_entity.html`, `contract_search_results.html`, and `partials/linkrow.html`. Compare two contract detail/edit hierarchies using active/inactive contracts, individually/consolidated billing, date periods, populated/empty identifiers, and publisher/journal search and selected states. Preserve field names/IDs, ARIA semantics, response roots/selectors, and HTMX targets/swaps for identifier rows, publisher/journal search, and adding/removing selected entities. Show light/dark and responsive states. Actions may remain inert; do not change production templates.

## Comments

Preview: [Contract administration layouts](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/contract-administration/index.html?variant=terms). Use the floating arrows to compare `terms` and `board`; **View** opens a contract and **Edit contract** opens its form.

The directory shows an active individually billed contract and an inactive consolidated contract. A · Terms first puts the period and billing up front, then identifiers and linked entities. B · Agreement board keeps status, billing, and identifiers in a rail while publisher/journal scope leads the detail. The shared edit surface reorders contract terms, identifier rows, and publisher/journal search and selected formsets between the two layouts.

Search result, selected-entity, and identifier controls retain the production form names/IDs and HTMX targets/swaps. Static data and actions are inert. Browser smoke covered both layouts, active/inactive records, date/billing/identifier states, HTMX attributes, and a 390px viewport; no console errors. [Source file](../prototypes/contract-administration/index.html), captured on local branch `prototype/contract-administration` at commit `42e5abd`; date-row refinement at `a351fec4`.

## Answer

Choose **A · Terms first**. Put contract period, billing, and identifiers ahead of publisher/journal associations; keep those associations available but secondary because users rarely link them. Preserve existing publisher/journal search and selected-entity HTMX contracts. No production templates or behavior changed.

## Follow-up

The selected A editor hierarchy now places Contract name and Publication billing across the full form width, with Start date and End date aligned together on desktop. Narrow layouts stack the fields. Captured on the same prototype branch at `a351fec4`.

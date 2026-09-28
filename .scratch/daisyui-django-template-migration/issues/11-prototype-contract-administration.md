# Prototype DaisyUI contract administration workflows

Status: open
Type: prototype
Blocked by: 09

## Question

How should the contract directory and management screens present contract status, billing mode, identifiers, and linked publishers/journals after the DaisyUI cutover? Create a throwaway prototype based on `contracts/contract_create.html`, `contract_detail.html`, `contract_list_item.html`, `contract_active_status.html`, `contract_search_add_entity.html`, `contract_search_results.html`, and `partials/linkrow.html`. Compare two contract detail/edit hierarchies using active/inactive contracts, individually/consolidated billing, date periods, populated/empty identifiers, and publisher/journal search and selected states. Preserve field names/IDs, ARIA semantics, response roots/selectors, and HTMX targets/swaps for identifier rows, publisher/journal search, and adding/removing selected entities. Show light/dark and responsive states. Actions may remain inert; do not change production templates.
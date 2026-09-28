# Prototype DaisyUI patterns for the invoice list

Status: resolved
Type: prototype
Blocked by: 06

## Question

Should the selected Triage queue treatment for funding requests carry over to invoice lists, or do invoice results need an invoice-specific ledger hierarchy? Create a throwaway UI prototype based on `invoices/invoice_list.html` and `invoices/invoice_list_item.html`, comparing three layouts that show invoice number, payment status, invoice date, creditor, total/currency, and warning state (foreign currency without conversion or invalid contract year). Preserve the shared right-side filter sidebar/mobile drawer, `#filter-sidebar-form`, `#filter-toolbar-form`, `#invoice-list`, and HTMX filter/chip contracts. Show paid/unpaid and warning examples in light/dark and responsive states. Keep production templates untouched; request/form actions can remain inert. Link the artifact and get the user's reaction on whether the funding-request Triage queue pattern generalizes or invoices need their own presentation.

## Comments

Preview: [Invoice list variants](http://127.0.0.1:8767/.scratch/daisyui-django-template-migration/prototypes/invoice-list/index.html?variant=ledger). Switch with the floating bar or `?variant=queue`, `?variant=ledger`, and `?variant=warning`; light/dark themes are available. Warnings now use inline or fixed-height indicators so they do not add a line to the invoice items. The shared filter drawer and search-select use CODA's existing JavaScript; HTMX requests are inert.

Source: branch `prototype/invoice-list-pattern`, commit `4781234f`, `.scratch/daisyui-django-template-migration/prototypes/invoice-list/index.html`. Desktop/mobile smoke verified equal row heights across warning and non-warning items; no browser errors. DaisyUI CDN is preview-only.

## Answer

Choose **B · Invoice ledger** for the invoice-specific hierarchy: number, creditor, date, total/currency, and payment status stay easy to scan. Match the funding-request list's subtle surface, thin border, and status-colored rail. Warnings must not change item height; render them as fixed-size inline markers (or in a reserved fixed-height slot), not extra text rows. Preserve the shared right-side filter/drawer and HTMX contracts.
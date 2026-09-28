# Choose a styling boundary for shadow search-selects

Status: resolved
Type: grilling
Blocked by: 04

## Question

The selected shared Django widget-template convention leaves two custom controls: `search-select` owns internal Shadow DOM CSS and exposes `::part(search-box)`; `search-select-multi` owns its dropdown and selected-option markup in a separate Shadow DOM. Where should their DaisyUI presentation live? Choose between component-owned Shadow DOM styles mapped to the light/dark DaisyUI theme, or adopting the shared DaisyUI stylesheet into the roots and using DaisyUI classes internally. Preserve keyboard filtering, slotted option contracts, form-associated values/validity, and external `::part` styling. A generic stylesheet-adoption helper exists but has no current call sites in these component scripts. The recommendation is to keep component-scoped styling mapped to the DaisyUI theme and use exposed parts, unless a visual proof shows that adopting the shared stylesheet meaningfully reduces CSS without changing behavior.

## Answer

Keep component-owned Shadow DOM styles for `search-select` and `search-select-multi`. Map their existing `--coda-*` values to the new light/dark DaisyUI theme tokens and retain the external `::part(search-box)` / `::part(search-input)` hooks. Do not wire the unused global stylesheet-adoption helper or adopt the full DaisyUI sheet into these roots as the default migration path. Preserve slotted options, keyboard filtering, form-associated values/validity, and document-level part styling.
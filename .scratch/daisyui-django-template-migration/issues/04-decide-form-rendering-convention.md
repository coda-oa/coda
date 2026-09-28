# Decide where shared Django form styling belongs

Status: resolved
Type: grilling
Blocked by: 03

## Question

Given the prototype, where should reusable DaisyUI field/control styling live across ordinary Django `form.as_p`/`form.as_div` output and `HtmxDynamicFormset` fragments (which also render fields through a custom inline template)? Choose the boundary between a shared form renderer/widget setup and template-level classes/layout. Keep field names, IDs, validation/error semantics, and HTMX fragment contracts unchanged; avoid duplicating control CSS across every app template.

## Answer

Use shared Django field/widget templates for reusable DaisyUI control classes and validation states; keep per-page templates responsible for layout, grouping, and the selected ledger table structure. This uses the existing `TemplatesSetting` renderer for both ordinary `form.as_*` output and HTMX formset fields rendered as `{{ field }}`. Custom widgets such as `search-select` remain explicit widget-template/component exceptions rather than per-page styling copies.
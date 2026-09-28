# DaisyUI Migration for CODA's Django Templates

## Destination

Convert the full CODA Django application UI from Pico CSS to daisyUI. Preserve the server-rendered UI structure and existing behavior, including HTMX updates; retain the current light/dark theme behavior and approximate blue/neutral palette while allowing visual divergence from Pico.

## Notes

- This effort includes implementing the cutover after the decision route is clear; it is not a specification-only handoff.
- The UI is Django-rendered with HTMX fragment responses. Preserve form names/IDs, ARIA semantics, HTMX attributes, response roots/selectors, and JavaScript hooks unless a ticket explicitly resolves otherwise.
- Institution search filtering in production remains server-side and returns HTMX updates; prototypes may simulate filtering locally for design review only.
- Keep the existing light/dark user preference and approximate CODA palette. Exact Pico visual parity is not required.
- Resolve tickets with `frontend-design`, `domain-modeling`, and `test-driven-development`; validate user-visible behavior through the existing browser tests and focused smoke checks.

## Decisions so far

- [Choose a production-safe DaisyUI CSS delivery path](issues/01-research-daisyui-css-delivery.md) — Official Django guidance supports a Node-free standalone compiler; build before `collectstatic` and scan all templates/HTMX fragments with complete class literals. Shadow DOM stylesheet adoption is not currently wired in the search-select components; migration must explicitly choose component-local styling or adoption, while keeping document `::part` rules. Corrected report on `research/daisyui-css-delivery` (`aad7b667`).
- [Decide how DaisyUI CSS enters production assets](issues/02-decide-css-build-path.md) — Use a locally compiled CSS asset from the standalone Tailwind CLI plus daisyUI bundle, generated before `collectstatic` and served by Django staticfiles/WhiteNoise; pin build artifacts and add no Node runtime or remote CSS dependency.
- [Prototype a DaisyUI pattern for the funding-request wizard](issues/03-prototype-wizard-form-pattern.md) — The user chose the compact, table-first “Ledger” treatment as the baseline form layout; existing form and HTMX contracts remain unchanged.
- [Decide where shared Django form styling belongs](issues/04-decide-form-rendering-convention.md) — Put reusable DaisyUI control classes and error states in shared Django field/widget templates; leave page templates to own layout and ledger tables.
- [Choose a styling boundary for shadow search-selects](issues/05-decide-search-select-styling.md) — Keep component-owned Shadow DOM CSS, map its `--coda-*` tokens to the DaisyUI light/dark theme, and retain external `::part` hooks; no stylesheet adoption wiring.
- [Prototype DaisyUI filters for the funding-request list](issues/06-prototype-filtered-fundingrequest-list.md) — Choose the Triage queue; place wrapping label pills below search and distinguish request rows with a subtle surface/border/status rail, not a heavy card. Preserve the right-side drawer and HTMX contracts.
- [Prototype DaisyUI patterns for the invoice list](issues/07-prototype-invoice-list-pattern.md) — Choose the invoice-ledger hierarchy with funding-request-style row surface/border/status rail; warning markers must not change item height.
- [Prototype a DaisyUI invoice-position editor](issues/08-prototype-invoice-position-editor.md) — Choose B · Expanded sections; align core fields on one desktop row and funding source type/source/split amount in shared columns across assignment rows.
- [Choose the next template group for DaisyUI design](issues/09-grilling-next-template-group.md) — Institution and contract administration is the next design priority; prototype the two workflows separately.
- [Prototype DaisyUI institution administration workflows](issues/10-prototype-institution-administration.md) — Combine A's tree directory with B's sectioned detail; keep matching nodes in place with uncounted ancestor context and production filtering server-side via HTMX.
- [Prototype DaisyUI contract administration workflows](issues/11-prototype-contract-administration.md) — Choose A · Terms first; prioritize billing and identifiers, with publisher/journal links secondary and existing HTMX contracts preserved.
- [Choose the next template group after contract administration](issues/12-grilling-next-group-after-administration.md) — Prioritize reference-data registries; keep operational/reporting surfaces in the map fog.
- [Prototype DaisyUI patterns for reference-data registries](issues/13-prototype-reference-data-registries.md) — Keep B as the preferred default and reuse A's sectioned details; add linked invoice/request references and a prototype-only Publisher detail while excluding the related pages/workflows and Blocklist from this prototype.
- [Choose the next template group after reference-data registries](issues/14-grilling-next-group-after-reference-data.md) — Prioritize Publication Vocabularies; prototype end-to-end limited-vocabulary administration.

## Not yet specified
- Detailed treatment of operational/reporting surfaces beyond Publication Vocabularies remains in fog until that prototype clarifies the route.

- Treatment of specialized data-entry/display tables and app-specific CSS in those groups.
- The complete browser-visible verification matrix for the app-wide cutover beyond current UI test coverage.

## Out of scope

- Pixel-for-pixel reproduction of Pico styling; visual divergence is explicitly acceptable.
- Changes to Django business flows or HTMX behavior unrelated to styling.

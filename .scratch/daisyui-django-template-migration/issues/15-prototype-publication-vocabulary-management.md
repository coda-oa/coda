# Prototype DaisyUI publication-vocabulary management workflows

Status: open
Assignee: @SvenMarcus
Type: prototype
Blocked by: 14

## Question

How should CODA present publication-vocabulary administration after prioritizing this area? Create a throwaway UI prototype for the end-to-end limited-vocabulary workflow: list base and limited vocabularies, create a limited vocabulary from a base, edit its name and hierarchical allowed/forbidden concepts with bulk selection and moves, save/cancel, and show usage-aware delete states. Preserve the existing vocabulary hierarchy, field names/IDs, ARIA semantics, and HTMX response roots/targets/swaps; keep actions inert and production templates untouched.

## Comments

Prototype artifact: [publication vocabularies](../prototypes/publication-vocabularies/index.html). Three layouts share the limited-vocabulary workflow: A · Split allowed/not allowed trees, B · One hierarchy with status tabs, and C · Vocabulary ledger.

Preview A: [open A](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/publication-vocabularies/index.html?variant=split).

Preview B: [open B](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/publication-vocabularies/index.html?variant=tabs).

Preview C: [open C](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/publication-vocabularies/index.html?variant=ledger).

Desktop browser smoke covered create-from-base, hierarchical search/level selection, allowed/forbidden moves, save/cancel/edit, and usage-aware deletion; 390px smoke covered all layouts and dark theme. No horizontal page overflow, browser errors, or console errors. The prototype is sample-only and leaves production templates untouched. Ticket remains open for human review.

Follow-up to user feedback: C is preferred, with a clearer selection flow. Its two independent filters are replaced by one concept/path search and All / Allowed / Not allowed filters with live result counts. A persistent selection summary shows allowed/not-allowed counts; Select visible, Clear selection, and Select by level are explicit, and bulk actions name their destination and activate only when applicable. After a move, C switches to the destination status filter. A and B remain available.

Updated preview C: [open C · Vocabulary ledger](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/publication-vocabularies/index.html?variant=ledger).

Desktop smoke covered search/path matches, mixed-status selection, filtered bulk moves, and destination switching; 390px smoke covered selection, search, theme, and no page overflow. A/B selection and move flows still work. No browser or console errors. The prototype remains open for human review.

Follow-up to user feedback: C now uses the same card-based vocabulary list as B; editing or creating a limited vocabulary still opens C's ledger editor. A and B remain unchanged.

Preview C · B card list + ledger editor: [open C](http://127.0.0.1:8770/.scratch/daisyui-django-template-migration/prototypes/publication-vocabularies/index.html?variant=ledger).

Desktop smoke confirmed B/C list rows and actions match and C retains its editor. At 390px, cards and the ledger editor fit without horizontal page overflow. No browser or console errors. [Source file](../prototypes/publication-vocabularies/index.html). Ticket remains open for human review.

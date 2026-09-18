# Filter Sidebar v2 — Review Fix Checklist

**Source:** PR-style review of `develop...feature/filter-sidebar-v2` (50 files, +4458/−452), 2026-09-17.
**Updated:** 2026-09-18, after `b3f5f18f` ("refactor: use htmx to re-render filter side bar to reduce js"). Line numbers re-anchored on that commit; anything marked *(review-time)* kept its old number because the file did not move. Anchors touched by the 2026-09-18 rebase onto `origin/develop` (`7ca48eeb`) are called out in "Delta from the rebase" rather than silently moved.
**Status:** Open — of the 6 P1 items, #1, #2 and #3 are closed; #4–#6 remain. Items are independent unless noted; checkbox syntax for tracking.
**Item numbers are stable** — closed items stay in place so old references keep resolving.

Verdicts: 6/8 reviewers request-changes, 2 approve-with-nits. Findings marked *(verified)* were independently confirmed against the code after the review pass.

## Delta from the review pass (b3f5f18f)

The region responses now re-render the entire sidebar from the URL (`<div hx-swap-oob="innerHTML:#filter-sidebar-form">` in both `*_filtered_list.html`), so the server's markup is the single source of widget state. Consequences for this list:

- **P1 #1 closed** — the client sync layer that created the race is deleted; removal is single-actor by construction.
- **P3 `resetSearchSelect` closed** — function deleted.
- **P1 #3 downgraded** — a wrong chip `source_id` can no longer corrupt state, only mis-point the flash. Its fix recipe is rewritten.
- **P3 focus item promoted to P2** — every sidebar change now replaces every control, so focus loss is the normal case, not an edge case.
- **Two new items**: region payload growth (P2 → Performance) and the dead `link_types` fixture spread (P2 → Tests).
- **P1 #6** re-worded: only the *toolbar* badge is stale now, and one fix option became trivial.
- Deleted by `b3f5f18f`: `ActiveFilter.value`, `data-remove-value`, `removeSelectedOption(value, {silent})`, `resetControl`/`resetSearchSelect`, `chip_remove_values` test reader. Its live pins are `swap_targets` (`tests/filterdom.py:28-42`), `test__*list_region__rerenders_the_sidebar_from_the_url` (both apps), `test__chip_removal__keeps_other_values_of_a_multi_value_filter` (`tests/fundingrequests/test_filter_forms_ui.py:183-199`, from the earlier fix), and four UI tests added by `b3f5f18f` (`:203-265`).

## Delta from the rebase (origin/develop @ 7ca48eeb, 2026-09-18)

The branch was rebased over 27 develop commits. Two stops: `0e590dde` (modify/delete on `invoices/invoice_filter_bar.html` → resolved with `git rm`; the branch had already replaced it with `invoice_filter_sidebar.html`, and develop's `invoice_list.html` include of it is gone from our tree) and `5e47275c` (content conflicts in `fundingrequests/views/listview.py`, `tests/fundingrequests/test_fundingrequest_search.py`, `tests/invoices/test_invoice_search.py`). Consequences for this list:

- **P1 #3 closed** — see its rewritten block. The chip now names `id_publication_states`.
- **P1 #2 stays closed, but its guard is no longer ours.** develop's `efe17d51` moved `map_or_none` into `src/coda/coda_itertools.py:45-58`, where it already catches `ValueError`; the branch's local guarded copy became dead code and was dropped at conflict time (`listview.py:61` imports the shared one). The `:172-179` / `:163-164` / `:195-203` anchors in item 2 are pre-rebase. The branch kept its own — and stronger — unparsable-input tests, so develop's 200-only duplicates were not restored.
- **No develop content was reverted and no branch file vanished.** `comm` of `git diff --name-only origin/develop..HEAD` against the pre-rebase diff is empty in both directions, and `git diff 4c9cfabd..HEAD` over develop's export-filter wiring (`exports/services/filter_form.py`, `contexts/exports/dto/filters.py`, `fundingrequests/forms/contract_dropdown.html`, `tests/exports/test_filter_form.py`, `tests/exports/test_applied_filters.py`) is empty.
- **develop fixed the export form's year input independently** (`4c9cfabd`: `contract_dropdown.html` is now `type="number" step="1"`), so the branch's two sidebar number inputs no longer duplicate it — they cover the sidebar, develop's covers the export dialog.
- **Two develop-side failures surfaced by the post-rebase suite**, neither caused by the branch:
  - `tests/apps/test_template.py::test__check_update_view__returns_banner_when_update_available` got a 403 body. develop's `ea425d42` ("enforce method and login gates") added `if not request.user.is_authenticated: raise PermissionDenied` (`src/coda/apps/views.py:29-30`) but left this one test without `@pytest.mark.usefixtures("logged_in")`, which its two siblings have. Fixed here by adding the fixture (`tests/apps/test_template.py:46`); the file is otherwise byte-identical to develop, and the test passes on the pre-rebase tree, so the defect came in with develop.
  - `tests/fundingrequests/wizard/test_fundingrequest_wizard.py::test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details[…]` fails on `assert actual is not None` (`repository.first()`), with the *parametrization moving between runs* and the file passing in isolation (92 passed). Reproduced on a clean `origin/develop` worktree, so it is develop-side, faker-driven flakiness — not a rebase casualty. Left alone.
- **Drawer work verified and completed during the post-rebase smoke.** `filter-drawer.js` had been trimmed to class+`aria-expanded`+Escape, so the narrow-screen overlay had no scrim, no scroll lock and no focus return. Added: `#filter-sidebar-backdrop` (`partials/filter_drawer.html:1-3`), its CSS plus `body.filter-drawer-open { overflow: hidden }` inside the `<1400px` block (`filter-sidebar.css:316-320, 349-372`), and backdrop-click / scroll-lock / focus-return in `filter-drawer.js:9-30`. Verified at 390×844: closed backdrop `visibility: hidden`; open `opacity: 1`, `z-index: 99`, body `overflow: hidden`, backdrop topmost at a point over the list; Escape with focus on `#filter-drawer-close` returns focus to `#filter-drawer-toggle`; backdrop click closes. At 1600px the backdrop is `display: none` and a stale body class does not lock scrolling (the lock rule lives inside the media query).

---

## P1 — Blocking (fix before merge)

### 1. ~~Chip × wipes ALL values of multi-value filters (request race)~~ — closed, obsoleted by `b3f5f18f` *(verified)*

- [x] Closed by server-side re-render, not by the original fix. `resetControl` no longer exists, so a × click is exactly one htmx GET and nothing else writes widget state. The race needs two actors; there is one.
- [x] Pinned by `test__chip_removal__keeps_other_values_of_a_multi_value_filter` (`tests/fundingrequests/test_filter_forms_ui.py:183-199`): after removing `approved`, the widget shows `rejected`, the chip row has one entry, and the URL keeps `processing_status=rejected`.
- [x] The original fix (silent-flag + per-value chip) was reverted in `b3f5f18f` as unconsumed. ~~Carry the removed value on the chip and reset only that value~~, ~~`data-remove-value`~~, ~~`resetControl` removes only that value~~, ~~`removeSelectedOption(value, { silent: true })`~~ — all dead references.
- Kept for history — the mechanism that made this a bug, and the reason the current design is shaped the way it is: `removeSelectedOption` dispatched `change`, which re-triggered `hx-trigger="change from:#filter-sidebar-form"` (`src/coda/apps/templates/partials/filter_layout.html:10`); htmx queues per issuing element, so the wipe-everything request could win against the chip's own GET.
- Affects (still true for any future client-side widget mutation): `processing_status`, `payment_status`, `payment_methods`, `open_access_type`, `exclude_labels`, `publication_states`.

### 2. ~~`contract_year` text input → uncaught `int()` ValueError → 500~~ — closed *(verified)*

- [x] Server guard, funding requests: `map_or_none` (`src/coda/apps/fundingrequests/views/listview.py:172-179`) swallows `ValueError` → `None`, so both `int()` call sites (`:163-164`) drop a hostile `contract_year` *and* a hostile `contract_name` instead of raising. Same idiom as `_label_ids` (`:195-203`).
- [x] Server guard, invoices: `_contract_year_criterion` (`src/coda/apps/invoices/views/inspect.py:56-61`) parses the param and returns `None` on `ValueError`; `_query_params_to_criteria` (`:64-79`) is annotated `... | None` and `build_query` (`:84-88`) skips `None`, so the raw string never reaches the `IntegerField` lookup (`invoices/models.py:74`). Deliberately untouched: `funding_source` (`:68`) still 500s on a non-numeric id, exactly as on develop, and the `contract_year: str | int` annotations in `invoice_query.py:139,203` stay.
- [x] `<input type="number" step="1" ...>` on both sidebars: `fundingrequests/fundingrequest_filter_sidebar.html:74-78`, `invoices/invoice_filter_sidebar.html:25-29`. No CSS keys on `input[type="text"]` (only `.search-wrapper input[type="search"]` in `forms.css:126`); the field is not `required`, so constraint validation blocks nothing.
- [x] The ignored value stays visible and removable — chips still render it and `filter_count` still counts it, which is what lets the user undo it. Pinned by `test__unparsable_contract_year__still_shows_a_removable_year_chip` (`tests/fundingrequests/test_active_filters.py:206-213`) and `test__step_mismatched_contract_year__region_renders_with_a_removable_year_chip` (`tests/invoices/test_invoice_list_view.py:252-260`); both list views by `test__bad_contract_year_param__is_ignored_by_filter` (`tests/fundingrequests/test_fundingrequest_search.py:299-308`) and `test__invoice_list_view__bad_contract_year_param__is_ignored_by_filter` (`tests/invoices/test_invoice_search.py:507-526`). No test pins the input `type` — it is browser convenience, not the contract.
- [x] Branch-only pins at the seam the guard lives on, added above the ported ones: `test__build_query__unparsable_contract_year__drops_only_the_year_criterion` + `test__build_query__contract_year__builds_the_year_criterion` (`tests/invoices/test_invoice_list_view.py:266-292`) assert the criterion list, so a bad year may drop *only* itself (`payment_status` beside it must survive) and a good year still yields `ContractYearCriterion(2024, positions_only=…)`; `test__unparsable_contract_id_filter__narrows_nothing` (`tests/fundingrequests/test_fundingrequest_list_view.py:281-290`) covers the second `int()` call site (`contract_name=abc`). Both mutations were run: develop's string-passing lambda fails the criterion tests and the ported ones; a `try` around the whole `build_query` loop — which also answers 200, so no view-level test notices — fails only the criterion test.
- **Cross-reference `4c9cfabd`** (develop, "fix(filters): enforce contract_year as an integer end to end"), which is not an ancestor of this branch; landed here as `5e47275c`. The guards and both sidebar inputs mirror its text verbatim, so the pending rebase collapses them into upstream's. Both ported tests were renamed to `..._is_ignored_by_filter` and the invoice one now asserts the result set, so after the rebase **both** this pair and develop's weaker `..._is_ignored_instead_of_500` originals survive side by side — delete develop's two (they assert `status_code == 200` and nothing else). Still arriving from that rebase, and deliberately not ported here: `fundingrequests/forms/contract_dropdown.html:16` (still `type="text"`, used by `exports/generate_export_form.html:47`, not a list sidebar), the export form → DTO → search-params wiring, and the hunk in the already-deleted `invoices/invoice_filter_bar.html`.
- Note after `b3f5f18f`: a 500 response carried no OOB sidebar markup, so the sidebar kept the values that just errored. Moot now — the request succeeds, and the region re-renders with the bad year echoed back into the field.

### 3. ~~Clean-but-broken merge with develop: publication-state chip source_id~~ — closed *(verified)*

- [x] Rebased on develop 2026-09-18. Develop's `40b5abaa` had converted `fundingrequests/forms/publication_state.html` to `<search-select-multi id="id_publication_states">`; the branch did not touch that file, so the merge was silent and `filter-chips.js`'s `document.getElementById(chip.dataset.source)` no-op'd on the old id.
- [x] Chip `source_id` is now `"id_publication_states"` (`src/coda/apps/fundingrequests/views/listview.py:304`).
- [x] Every other chip `source_id` re-checked against post-rebase control ids — `processing_status`, `id_payment_status`, `payment_methods`, `open_access_type`, `publication_type_{v}`, `id_start_date`, `id_end_date`, `contract_name`, `contract_year`, `invalid_contract_years`, `label-pills`, `exclude_labels` — all present.
- [x] Pinned generically, not per-field: `test__every_chip__points_at_a_control_present_in_the_response` (`tests/fundingrequests/test_active_filters.py`) collects every `id` in the region response and fails on any chip naming a control that is not there. Mutation-checked: putting the f-string back fails it with `{'Published': 'publication-state-Published'}`. It guards the next widget rename in either app, which is what make-whole-one silently broke.
- [x] Verified live: `/fundingrequests/list/?publication_states=approved` renders `data-source="id_publication_states"` and `document.getElementById` resolves it to the `SEARCH-SELECT-MULTI`.
- **Why it was never blocking:** widget state comes from the server and chip removal uses `remove_fragment_url`; `data-source` is consumed only by the flash handler (`src/coda/apps/static/js/filter-chips.js:18-34`), so a stale id mis-points a highlight rather than corrupting state.

### 4. Invalid date range: warning swallowed, multiplied, and chips lie

- [ ] Region responses render no messages block (`invoices/invoice_filtered_list.html:7-8`, `fundingrequests/fundingrequest_filtered_list.html:7-11`; `base.html:113-119` renders messages outside the swap target) → `messages.warning` from `build_query` queues in the session and surfaces on a later unrelated full-page load, while `From/To` chips still render, claiming an active filter that `build_query` silently dropped (`src/coda/apps/invoices/views/inspect.py:86-87`; `src/coda/domain/date.py:21-23`). Native `type=date` does not enforce start ≤ end.
- [ ] Each HTMX partial re-queues the warning per keystroke/change tick (`src/coda/apps/fundingrequests/views/listview.py:148-150`, reused by `FundingRequestListRegionView`) → floods the capped-20 session message queue and can evict genuine save/import messages.
- [ ] Fix: skip `messages.warning` when `request.headers.get("HX-Request") == "true"`, and either OOB a messages partial into the fragment response (matching container id in `base.html`) or suppress/flag date chips when the range is invalid. Coordinate FR + invoice sides; same defect both apps.

### 5. `contract_positions_only`: invisible, unremovable invoice filter

- [ ] Reachable via openCost deep link (`src/coda/apps/templates/opencost/report_detail.html:185`, already on develop). Not in `_filter_single_value_fields` (`src/coda/apps/invoices/views/inspect.py:43-52`), no chip, no sidebar control; removing the "Contract" chip leaves it applied to the next contract choice. Violates `build_active_filters`' documented count↔chip invariant.
- [ ] Still invisible after `b3f5f18f`: the sidebar re-renders from the URL, but a param with no control and no chip renders as nothing.
- [ ] Fix option A: add to `_filter_single_value_fields`, emit a chip, add a sidebar checkbox so the deep link's intent is visible and removable.
- [ ] Fix option B: extend `listfilters.remove_value_url` (`src/coda/apps/listfilters.py:68-87`) with `also_remove: Sequence[str] = ()` and pass `("contract_positions_only",)` for contract chips.

### 6. Toolbar filter-count badge goes stale

- [ ] `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html:18-25` — the badge is outside every swap target. The *sidebar* header count (`partials/filter_header.html:4`) does update on every change because it rides inside the swapped form; the toolbar badge does not, and on mobile (drawer closed) it is the only filter indicator, so it misleads in both directions.
- [ ] Fix: stable id on the badge + matching `hx-swap-oob` copy in the region response template, or sync from the swapped header's `.filter-count` in shared JS. The second option got cheaper in `b3f5f18f`: the header is now guaranteed to re-render with every response, so reading `.filter-count` from it in one place is reliable.

---

## P2 — Medium (land in one pass)

### Performance

- [ ] **Region payload grew 7.3× by design — scale it with the contract table.** *(new 2026-09-18, measured)* The fragment response went 1201 B → 8831 B (`?processing_status=approved`; 1 contract, 3 funding requests, no matching rows). It scales linearly with `contract_list`: 60 contracts → 14392 B, i.e. **≈94 B per contract row** — ~+47 KB per region GET at 500 contracts. Paid on every sidebar change *and* every `input delay:300ms` toolbar keystroke burst. Mitigation candidates: render contract options lazily into the sidebar, cap/paginate `contract_list`, or accept and size the CI/browser budget accordingly. See "Measured on `b3f5f18f`" for the query-count half of this.
- [ ] Invoice region materializes the entire result set per keystroke: `src/coda/apps/invoices/views/inspect.py:193` `list(search_to_list_items(...))` feeds the Paginator; FR converts only the page via `LazyBulkQuerySet` (`src/coda/apps/domainqueryset.py:130-152`). Make the invoice path sliceable (offset/limit or LazyBulkQuerySet-style sequence).
- [ ] Region view inherits an eager `Institution.objects.all()` via `funding_sources_context()` (`src/coda/apps/invoices/views/inspect.py:182`; `funding_source_service.py:46`) — never read by the fragment. Add an `include_institutions=False` flag or override `get_context_data` on the region subclass.
- [ ] `src/coda/apps/fundingrequests/views/listview.py:180` builds `contract_list` unconditionally (`get_contract_list_context`), and `build_active_filters` evaluates it via `get_context_data` (`listview.py:117`) even with no `contract_name` filter — per-request overhead for chip building. Build lazily inside the branch (invoices already do). Note: `b3f5f18f` did **not** add a query here, precisely because the chip builder already forces evaluation.

### HTMX request hygiene

- [ ] 2–3 identical region GETs per single dropdown selection: synthetic `dispatchChangeEvent` + composed native `change` from the shadow input (`src/coda/apps/static/js/search-select.js:164,179,196`; `search-select-multi.js:184`). Let the composed native change be the single trigger, or dedupe by emitted value in `dispatchChangeEvent`. Cost got worse in `b3f5f18f`: each duplicate response re-renders the whole sidebar, so the second swap re-creates the widget the user is still interacting with. Measured caveat: for `search-select-multi` option clicks the duplication did not reproduce in Chromium — one region GET per pick (instrumented `htmx:beforeRequest`). Re-check per widget before spending effort.
- [ ] `filter_count` counts empty-string `publication_type=` (`src/coda/apps/listfilters.py:50-54`) but `build_active_filters` renders no chip → "1" badge over an empty chip row. Treat empty as inactive in `count_active_filters`.

### UI correctness / consistency

- [ ] **Focus is never restored to the control the user just used — promoted from P3.** `src/coda/apps/static/js/filter-drawer.js:12-15` has no focus management. `b3f5f18f` turned this from an edge case into the normal path: every sidebar change replaces every control inside `#filter-sidebar-form`, so focus lands on `<body>` after each pick and a second multi-select pick requires re-clicking the widget. Nothing pins it — `test__sidebar_rerender__keeps_mobile_drawer_open` asserts drawer class, not focus. Suggested: capture the active control's id before the swap and restore by id in an `htmx:afterSwap` handler (the swap is id-addressable, which is exactly what makes this cheap).
- [ ] Invoice sort control shows "Alphabet" while the view defaults to `date_desc` (`src/coda/apps/templates/invoices/invoice_filter_toolbar.html:10-16` vs `inspect.py:192` / `invoice_query.py:290`); first sidebar change silently re-sorts. Add `{% if not request.GET.sort_by %}selected{% endif %}` to the `date_desc` option. The toolbar is never swapped, so this stays stale until a full page load.
- [ ] Label-kind chips styled only via accidental collision with `.label` in `src/coda/apps/static/css/fundingrequests.css:109-117`; load-order-fragile and size-inconsistent with neutral chips. Add explicit `.active-filter.label` block in `filter-sidebar.css`.
- [ ] Page-object duplication has already drifted, and `b3f5f18f` widened it: `tests/page_objects/invoice_list_page.py:67-70` still missing the `_wait_for_settled()` call the FR version has, and the FR page object gained `navigate(query=...)` (`fundingrequest_list_page.py:19-23`) plus `click_active_filter_body` (`:77-79`) with no invoice counterpart. Extract a `FilterListPage` base owning toolbar/active-filters/settle machinery, parameterized by list-region id.
- [ ] `_wait_for_settled` is provably vacuous for the `input delay:300ms` path (no `.htmx-request` exists during the 300 ms delay) — `tests/page_objects/fundingrequest_list_page.py:152-155`, `invoice_list_page.py:129-132`. Replace with an htmx-lifecycle in-flight counter (`htmx:configRequest`/`htmx:afterRequest`/`htmx:sendError` → `window.__htmxInflight`), or drop the wait and document when settle is meaningful. Confirmed practical: a `htmx:beforeRequest` counter installed via `add_init_script` gave exact per-change request counts during the `b3f5f18f` work.

### Tests

- [ ] `tests/fundingrequests/test_active_filters.py:121` *(verified)*: `sort_by="date-asc"` is not a real value (product emits `date_desc`/`date_asc`/`alphabetical`); passes only via silent fallback. Use `date_asc`.
- [ ] No test pins the `HX-Push-Url` contract **at unit level** (`src/coda/apps/listfilters.py:26-35`): header present with `HX-Request: true`, absent on plain GET. Partially covered by `b3f5f18f`: a sidebar change GETs the bare region URL with no `hx-push-url` attribute, so the query string asserted by `test__deep_linked_selection__survives_the_next_filter_change` and `test__sidebar_rerender__keeps_hydrated_selection_in_the_next_request` can only come from `_push_url` — dropping the query breaks both. Still missing: the header-present/absent assertion on a plain and an htmx GET.
- [ ] Invoice suite lacks invariants FR has: `filter_count == len(active_filters)` parity; chip-removal round trip (GET `remove_url`, assert widened result + no `page=`); pagination link preserves active filters; anonymous request → 302 for both `invoices:list` and `invoices:list_region`.
- [ ] Empty-param serialization risk: htmx sends `date_start=&search_term=&...` → `request.GET` truthy → `src/coda/apps/templates/invoices/partials/invoice_list_region.html:3` can render "No invoices match the selected filters" for a genuinely unfiltered empty list. Pin current behavior in a test; consider dropping empty values in `remove_value_url` and/or the empty-state condition. `b3f5f18f` neither fixes nor worsens it, but its UI tests depend on those empty params reaching the URL, so a change here must re-check `should_have_url_query` expectations.
- [ ] Dead `link_types` fixture requests — **spread from 1 to 6 sites** (`tests/fundingrequests/test_filter_forms_ui.py`). The fixture (`conftest.py:44-48`) exists only to create article/monograph funding requests, so it is dead in every test that creates none: `:114-117` (pre-existing, contract only), `:183-187`, and the four added by `b3f5f18f` (`:205-207`, `:219-221`, `:235-237`, `:251-253`). Remove it from those signatures, or comment where it is load-bearing.
- [ ] `tests/fundingrequests/test_filter_forms_ui.py` chip-reset test also carries a tautology: unchecked `#publication_type_article` is implied by checked `#publication_type_all` (radiogroup exclusivity). Replace with `should_not_have_url_query("publication_type=article")` or drop.
- [ ] Page objects key on widget internals (`#search-box`, `.option`, `.selected-tag`, form-control ids) where `tests/filterdom.py`'s philosophy (field names + visible text) governs; confine raw ids to OOB swap targets and widget-driver helpers. `b3f5f18f` added two more keying styles to fold in: control ids (`#processing_status`) and the layout class (`.filter-layout` + `filter-drawer-open`).
- [ ] The sidebar re-render's swap boundary is id-coupled and now deliberately pinned: both region templates target `#filter-sidebar-form` by CSS id (`innerHTML:#filter-sidebar-form`), and the response is only correct if that id survives. Renaming the form silently no-ops the whole design — htmx logs nothing user-visible. `test__*list_region__rerenders_the_sidebar_from_the_url` (both apps) plus `swap_targets` (`tests/filterdom.py:28-42`) fail on that, so treat those assertions as the contract, not as duplication.

---

## P3 — Low / nits

### CSS / markup

- [ ] Dead `#search-form .button` rule in `src/coda/apps/static/css/button.css:68` — orphaned by deleting both `fundingrequest_filter.html` and `invoice_filter_bar.html`. Delete the rule.
- [ ] `src/coda/apps/static/css/filter-sidebar.css:11-14`: sticky sidebar `height: 100dvh` with `top: 1rem` clips its bottom 1rem below the fold permanently. Use `max-height: calc(100dvh - 2rem)` (also makes the drawer block's `max-height: none` at :323 meaningful again).
- [ ] `src/coda/apps/static/css/filter-sidebar.css:98-100`: `.active-filters:empty` never matches — Django emits whitespace text nodes. Use `.active-filters:not(:has(.active-filter))` or `{% spaceless %}` around the loop. Unchanged by `b3f5f18f`; the chip row is now swapped wholesale, which does not remove the whitespace.
- [ ] Invoice sidebar data-quality toggles lost `role="switch"` present in the deleted `invoice_filter_bar.html` and in the FR sidebar (`src/coda/apps/templates/invoices/invoice_filter_sidebar.html:37-59`); `aria-checked` on a bare checkbox is discouraged and goes stale on manual toggle. Restore `role="switch"` on all three. Server-rendered `aria-checked` is now re-emitted on every change, so it no longer goes stale after a filter update — only after a local, request-less toggle.
- [ ] FR toolbar search input named only by placeholder (`src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html:2-6`); add `aria-label="Search funding requests"` or a visually-hidden label.

### JS / a11y

- [ ] `src/coda/apps/static/js/filter-drawer.js:29-33`: Escape closes the whole drawer when a select dropdown is open (drawer `keydown` runs before select `keyup`). Ignore Escape whose `composedPath` originates in the selects' shadow inputs. `search-select-multi` also never closes its dropdown on Escape — follow-up.
- [ ] ~~`filter-chips.js:50-63`: `resetSearchSelect` leaves stale `el.activeElement` and its `.focus` class — clear both before `resetFilter()`.~~ **Closed** — `resetSearchSelect` was deleted in `b3f5f18f`; the chip body's only job now is the flash (`filter-chips.js:18-34`), which touches no widget internals.
- [ ] Pre-existing (not a blocker here, needs follow-up ticket): unescaped `innerHTML` interpolation in `src/coda/apps/static/js/search-select-multi.js:229-239` (`${text}`, `${value}`, `${color}`); user-editable label names flow in → stored-XSS vector. Rebuild those nodes with `createElement`/`textContent`. Unchanged in kind by `b3f5f18f` (tags were already hydrated from `selected` options), but the tags now rebuild on every filter change instead of once per page load, so a fix here also removes repeated innerHTML churn from the hot path.

### Packaging

- [ ] `src/coda/apps/templates/base.html:71-98`: `filter-sidebar.css` + `filter-drawer.js` + `filter-chips.js` load site-wide for 2 routes. Matches existing repo convention (page sheets are linked globally too), so optional: move to a per-page `{% block extra_head %}`. `filter-chips.js` shrank 75 → 36 lines in `b3f5f18f`.

### Docs

- [ ] Sidebar design spec still "Draft for review" (`docs/superpowers/specs/2026-09-01-funding-request-filter-sidebar-design.md:4`) while shipped; promote or amend to "Implemented with amendments".
- [ ] Spec contradicted by shipped code, needs an amendment section: "No chip row" (:66) vs shipped `#active-filters` chips + `filter-chips.js`; "No new endpoint needed" / full-page response (:110) vs dedicated `list/region/` endpoints + `ListRegionMixin` HX-Push-Url; single-form (:109) vs two forms with `input delay:300ms`; invoice migration + shared `listfilters.py` explicitly out of scope (:5, :119-123) yet ~half the PR; sidebar width 250 px in docs vs shipped `width: 280px` (`filter-sidebar.css:9`); control table (:71-85) omits `publication_states`. Add: the spec's widget-state story is now "server re-renders the sidebar on every region response" — no client sync layer exists.
- [ ] Both plans: 0/83 checkboxes checked while their work shipped; per-task commit recipes don't match squashed history. Check off or banner "Historical — implemented in aaf67c8f+; do not execute".
- [ ] Sidebar plan Task 6 (:837-856) `git rm`s `status_dropdown.html`/`payment_method.html`/`publication_type.html` — all still included by `exports/generate_export_form.html`; executing it 500s the export page. Rewrite Task 6.
- [ ] Sidebar plan :820 + Task 3 snippet place the sidebar left; spec and shipped layout put it right. Fix.
- [ ] Drawer docs reference files that never existed (`fundingrequest_filter_drawer.html`, `partials/fundingrequest_filter_header.html` vs shipped `partials/filter_*.html`), a fictional `14 passed` baseline (×6), and left-docked layout. Correct or banner.
- [ ] Delete personal-machine path at plan :917 (`/Users/marcus/...` — confirmed; leaks username into repo history).
- [ ] Refresh spec problem-statement (:10) / bug item (:115): develop 40b5abaa already converted all filter pickers to `search-select-multi` before the docs were committed.

---

## Verified clean (do not re-litigate)

- MRO/auth: `ListRegionMixin` defines no `dispatch`, so `LoginRequiredMixin.dispatch` wins on both region views; region-vs-page context correct in both directions; no route/URL-name collisions.
- Server-side escaping: chips render via autoescape, no `|safe`/`mark_safe`; `remove_value_url` percent-encodes; no XSS in the Python/template chip path.
- Cutover: zero dangling references to `fundingrequest_filter.html` / `invoice_filter_bar.html` / `expand_advanced_search`; every old control present in new toolbar/sidebar.
- `search-select.js` rewrite is behavior-preserving vs develop (only `dispatchChangeEvent` additions + `top: 100%` positioning are semantic).
- `fundingrequests.css` +109/−97 collapses under `git diff -w` to 14/2: whitespace/formatting plus two real `.coda-label-pills` rules.
- Drawer breakpoint classes match `filter-drawer.js` exactly; JS is breakpoint-agnostic so the 1400px threshold can't drift; zero `!important` in new CSS; all `var(--coda-*)` resolve against `vars.css`.
- `labels` param single-sourced (hidden inputs in toolbar pills; no competing control); no form nesting; id/name contracts hold on-branch.
- UI test suite: outcome-level assertions, expect()-auto-waiting, transactional isolation, viewport pinned; `journal_modal.py` deletion confirmed dead.

## Measured on `b3f5f18f` (don't re-derive)

- **htmx binds `change from:#selector` to the element node.** Swapping the `<form id="filter-sidebar-form">` element itself (whole-form `hx-swap-oob="true"`) orphans the listener: after the first swap, further sidebar changes issued zero requests (instrumented `htmx:beforeRequest` stayed flat; no console error). That is why the boundary is `innerHTML:#filter-sidebar-form`, and why the form element must survive.
- **Region request count is unchanged by the re-render: 7 queries before and after** the same region GET. The added cost is bytes and template rendering, not SQL.
- **Chromium fires `formAssociatedCallback` twice around insertion of a form-associated custom element** (`F:0 → connectedCallback → F:1 → F:1` on swap; `connectedCallback → F:1` on initial parse). So a hydrated `search-select-multi` reaches the correct form value today without help; `search-select-multi.js:255-258` states the invariant explicitly because the ordering is engine-specific. `search-select` is unaffected — it has no `formAssociatedCallback` and sets its value from `slotchange`.
- **Modal UI flakiness is pre-existing.** `tests/journals/test_journal_modal_ui.py` + `tests/publishers/test_publisher_modal_ui.py` fail 3/10 on two consecutive runs at `b587e164` (clean source, verified via a worktree with `PYTHONPATH` pointing at the worktree's `src`), with the failing set moving between runs, and pass in isolation. Unrelated to the sidebar work. Caveat for future baselines: `coda.pth` pins `/app/src` on `sys.path`, so a worktree alone does **not** isolate `src` or templates — `PYTHONPATH` must override it.

- **Baseline recipe that isolates `src`, templates *and* statics:** run the tree in a one-off container of the current dev image with the worktree bind-mounted at `/app` — `docker run --rm -u dev-user -v /tmp/<wt>:/app -w /app --network coda_default -e DATABASE_URL=… coda_local_django pdm run pytest …`. `coda.pth`'s `/app/src` then resolves inside the worktree, so no `PYTHONPATH` override is needed. Used 2026-09-18 to attribute both post-rebase failures to develop. One pytest process at a time: they share the test database.
- **One region GET per sidebar edit, confirmed in the browser.** Four keystrokes into `#contract_year` plus a blur produced exactly one `htmx:beforeRequest` / `htmx:afterRequest` pair and one `/list/region/?…contract_year=20.5` resource entry on the FR list, and one request on the invoice list. Count requests with an `htmx:beforeRequest` listener on `document` *and* resource timing; a counter installed after several swaps had already happened can record nothing while requests demonstrably succeed, so cross-check the two.

## Suggested sequencing

1. ~~Rebase on develop~~ — **done 2026-09-18** (`7ca48eeb`); #3 closed, all chip source_ids re-verified, drawer overlay finished.
2. P1 #4, #5, #6 — #1 needs no work, #2 closed on this branch (mirrors develop's `4c9cfabd`).
3. P2: focus restoration (promoted item) + performance cluster, deciding the contract-list question in the new payload item before the other perf items, since it sets the per-request budget.
4. P2 test gaps + the dead-fixture cleanup.
5. P3 nits + docs amendments.
6. Follow-up ticket: `search-select-multi` innerHTML XSS.

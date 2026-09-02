# Funding Request Filter Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Below a 1400px viewport, the funding request list's filter sidebar becomes an off-canvas right-edge drawer (no scrim) toggled from the toolbar, while ≥1400px stays exactly as it is today.

**Architecture:** One DOM node serves both modes. A CSS media query restyles the existing `<aside class="filter-sidebar">` as a fixed drawer translated off-canvas; ~20 lines of vanilla JS toggle a `filter-drawer-open` class on `.filter-layout`. The sidebar markup moves into a new partial (`fundingrequest_filter_drawer.html`); the toolbar gains a `type="button"` toggle; the drawer header gains a × close button. No view, URL, HTMX, or query-param changes — the existing `change from:#filter-sidebar-form` triggers keep working in both modes.

**Tech Stack:** Django templates (djlint-formatted), plain CSS (tokens from `vars.css`), vanilla JS. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-funding-request-filter-drawer-design.md`

**Environment:** All Python/pdm/djlint commands run in the dev container:
`docker exec -u dev-user -w /app coda_local_django bash -lc '<command>'`

**Verification baseline after every task:**
`docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -q'`
Expected: `14 passed` (no new automated tests were approved — the existing tests are the regression net).

---

### Task 1: Extract sidebar into a drawer partial

**Files:**
- Create: `src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html`
- Modify: `src/coda/apps/templates/fundingrequests/fundingrequest_list.html:5-9`

- [ ] **Step 1: Create the drawer partial**

Create `src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html`:

```html
<aside class="filter-sidebar">
    <form method="get" id="filter-sidebar-form">
        {% include "fundingrequests/fundingrequest_filter_sidebar.html" %}
    </form>
</aside>
```

- [ ] **Step 2: Use the partial in the list page**

In `src/coda/apps/templates/fundingrequests/fundingrequest_list.html`, replace the inline `<aside>` block (currently lines 19-23):

```html
        <aside class="filter-sidebar">
            <form method="get" id="filter-sidebar-form">
                {% include "fundingrequests/fundingrequest_filter_sidebar.html" %}
            </form>
        </aside>
```

with:

```html
        {% include "fundingrequests/fundingrequest_filter_drawer.html" %}
```

- [ ] **Step 3: Verify**

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run djlint --check src/coda/apps/templates/fundingrequests/fundingrequest_list.html src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html'`
Expected: `0 files would be updated.` (run `pdm run djlint <same files>` without `--check` and re-check if it reports changes)

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -q'`
Expected: `14 passed`

- [ ] **Step 4: Commit**

```bash
git add src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html src/coda/apps/templates/fundingrequests/fundingrequest_list.html
git commit -m "refactor(fundingrequests/list): extract filter sidebar into drawer partial"
```

---

### Task 2: Toolbar toggle button

**Files:**
- Modify: `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html`
- Modify: `src/coda/apps/static/css/fundingrequests.css` (append at end of file)

- [ ] **Step 1: Add the button to the toolbar**

In `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html`, add the button after the `</label>` of the sort control (i.e. as the last child of `.filter-toolbar`, before its closing `</div>`):

```html
    <button type="button" id="filter-drawer-toggle" class="filter-drawer-toggle">
        Filters{% if filter_count %} <span class="filter-count">{{ filter_count }}</span>{% endif %}
    </button>
```

Note: `filter_count` is already in the view context for this page; the button is `type="button"` so it never submits the toolbar form.

- [ ] **Step 2: Add button CSS (hidden on wide screens, visible below 1400px)**

Append to `src/coda/apps/static/css/fundingrequests.css`:

```css
/* Filter drawer toggle (narrow screens) */
.filter-drawer-toggle {
    display: none;
}

@media screen and (width < 1400px) {
    .filter-drawer-toggle {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: var(--coda-form-element-spacing-vertical) var(--coda-form-element-spacing-horizontal);
        font-size: 0.85rem;
        border: var(--coda-border-width) solid var(--coda-border-color);
        border-radius: var(--coda-border-radius);
        background: var(--coda-form-element-background-color);
        color: var(--coda-color);
        cursor: pointer;
    }
}
```

- [ ] **Step 3: Verify**

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run djlint --check src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html'`
Expected: `0 files would be updated.`

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -q'`
Expected: `14 passed`

- [ ] **Step 4: Commit**

```bash
git add src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html src/coda/apps/static/css/fundingrequests.css
git commit -m "feat(fundingrequests/list): add filter drawer toggle to toolbar"
```

---

### Task 3: Close button in the drawer header

**Files:**
- Modify: `src/coda/apps/templates/fundingrequests/partials/fundingrequest_filter_header.html`
- Modify: `src/coda/apps/static/css/fundingrequests.css` (append at end of file)

- [ ] **Step 1: Add the × button to the header partial**

The current file ends with:

```html
    {% if filter_count %}
        <a href="{% url 'fundingrequests:list' %}" class="filter-clear">Clear all</a>
    {% endif %}
</div>
```

Insert the close button before the closing `</div>` (after the `{% endif %}`):

```html
    <button type="button"
            id="filter-drawer-close"
            class="filter-drawer-close"
            aria-label="Close filters">×</button>
```

(Note: djlint H023 forbids entity references, so use the literal `×` character; djlint reflows the attributes as shown. Run the `djlint-reformat-django` pre-commit hook on the file.)

Note: this header is the HTMX out-of-band swap target (`#filter-sidebar-header`), so its DOM is replaced after every filter change. Task 5's JS therefore uses event delegation and never attaches a listener to this button directly.

- [ ] **Step 2: Add close-button CSS (hidden on wide screens, visible below 1400px)**

Append to `src/coda/apps/static/css/fundingrequests.css`:

```css
/* Filter drawer close (narrow screens) */
.filter-drawer-close {
    display: none;
}

@media screen and (width < 1400px) {
    .filter-drawer-close {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.75rem;
        height: 1.75rem;
        border: 0;
        border-radius: var(--coda-border-radius);
        background: transparent;
        color: var(--coda-muted-color);
        font-size: 1.1rem;
        cursor: pointer;
    }

    .filter-drawer-close:hover {
        background: var(--coda-primary-background-hover);
        color: var(--coda-validation-text-color);
    }
}
```

- [ ] **Step 3: Verify**

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run djlint --check src/coda/apps/templates/fundingrequests/partials/fundingrequest_filter_header.html'`
Expected: `0 files would be updated.`

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -q'`
Expected: `14 passed`

- [ ] **Step 4: Commit**

```bash
git add src/coda/apps/templates/fundingrequests/partials/fundingrequest_filter_header.html src/coda/apps/static/css/fundingrequests.css
git commit -m "feat(fundingrequests/list): add close button to filter drawer header"
```

---

### Task 4: Drawer CSS (off-canvas + slide)

**Files:**
- Modify: `src/coda/apps/static/css/fundingrequests.css` (append at end of file)

- [ ] **Step 1: Add the drawer media query**

Append to `src/coda/apps/static/css/fundingrequests.css`:

```css
/* Filter drawer (narrow screens) */
@media screen and (width < 1400px) {
    .filter-sidebar {
        position: fixed;
        top: 0;
        right: 0;
        bottom: 0;
        max-height: none;
        padding: 1rem;
        box-sizing: border-box;
        background: var(--coda-background-color);
        box-shadow: -2px 0 8px rgb(0 0 0 / 0.15);
        transform: translateX(100%);
        transition: transform 0.2s ease;
        z-index: 100;
    }

    .filter-drawer-open .filter-sidebar {
        transform: translateX(0);
    }
}
```

Notes:
- The existing `.filter-sidebar` rule (`width: 250px; flex-shrink: 0; position: sticky; top: 1rem; max-height: calc(100vh - 2rem); overflow-y: auto`) is left untouched; the media query overrides `position`, `top`, `max-height`, and adds `padding` because the fixed drawer is no longer inside the padded page container.
- `z-index: 100` must sit above the list content and below any app-wide modal if one exists.
- `filter-drawer-open` lives on `.filter-layout`; the class only matters inside this media query, so it cannot leak into docked mode.

- [ ] **Step 2: Verify**

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -q'`
Expected: `14 passed`

- [ ] **Step 3: Commit**

```bash
git add src/coda/apps/static/css/fundingrequests.css
git commit -m "style(fundingrequests/list): restyle filter sidebar as off-canvas drawer below 1400px"
```

---

### Task 5: Drawer toggle JavaScript

**Files:**
- Create: `src/coda/apps/static/js/filter-drawer.js`
- Modify: `src/coda/apps/templates/base.html` (script section, after the `search-select-multi.js` tag)
- Modify: `src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html` (add `id` to the aside)
- Modify: `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html` (add disclosure aria attributes to the toggle)

- [ ] **Step 1: Add the aside id**

In `src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html`, change the first line:

```html
<aside class="filter-sidebar">
```

to:

```html
<aside class="filter-sidebar" id="filter-sidebar">
```

- [ ] **Step 2: Add disclosure aria attributes to the toggle**

In `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html`, change:

```html
    <button type="button" id="filter-drawer-toggle" class="filter-drawer-toggle">
```

to:

```html
    <button type="button" id="filter-drawer-toggle" class="filter-drawer-toggle" aria-controls="filter-sidebar" aria-expanded="false">
```

- [ ] **Step 3: Create the script**

Create `src/coda/apps/static/js/filter-drawer.js`:

```js
(function () {
    "use strict";

    const layout = document.querySelector(".filter-layout");
    const toggle = document.getElementById("filter-drawer-toggle");
    if (!layout || !toggle) {
        return;
    }

    const isOpen = () => layout.classList.contains("filter-drawer-open");

    const setOpen = (open) => {
        layout.classList.toggle("filter-drawer-open", open);
        toggle.setAttribute("aria-expanded", String(open));
    };

    toggle.addEventListener("click", () => {
        setOpen(!isOpen());
    });

    // Delegated: the × close button lives inside the OOB-swapped drawer
    // header, so its DOM node is replaced after every filter change.
    layout.addEventListener("click", (event) => {
        if (event.target.closest("#filter-drawer-close")) {
            setOpen(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isOpen()) {
            setOpen(false);
        }
    });
})();
```

- [ ] **Step 4: Load it in base.html**

In `src/coda/apps/templates/base.html`, after the existing line:

```html
        <script src="{% static 'js/search-select-multi.js' %}"
                crossorigin="anonymous"></script>
```

add:

```html
        <script src="{% static 'js/filter-drawer.js' %}"
                crossorigin="anonymous"></script>
```

The script self-guards (`return` when the toggle doesn't exist), so it is inert on every other page — matching the pattern of the other globally loaded `static/js` files.

- [ ] **Step 5: Verify**

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run djlint src/coda/apps/templates/base.html'`
Expected: exactly the 2 pre-existing errors (`H025 4:4` orphan `<head>`, `H037 5:59` duplicate attribute — the known corrupted `<head>`, unrelated to this work) and no new errors. Do NOT let djlint reformat base.html as part of this task (pre-existing drift; committing a whole-file reformat would bury the change).

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run djlint --check src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html'`
Expected: `0 files would be updated.`

Run: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -q'`
Expected: `14 passed`

- [ ] **Step 6: Commit**

```bash
git add src/coda/apps/static/js/filter-drawer.js src/coda/apps/templates/base.html src/coda/apps/templates/fundingrequests/fundingrequest_filter_drawer.html src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html
git commit -m "feat(fundingrequests/list): toggle filter drawer below 1400px"
```

---

### Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Lint, types, full unit test suite**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run ruff check .'
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run mypy'
docker exec -u dev-user -w /app coda_local_django bash -lc "pdm run pytest -m 'not integration' --ff -q"
```

Expected:
- ruff: no new findings
- mypy: exactly the 9 known pre-existing errors (in `htmx_components/converters.py`, `home.py`, `invoices/views/creditor.py`, `import_service/_service.py`), nothing new
- pytest: all pass (1149+ tests), 0 failures

- [ ] **Step 2: Manual browser checklist (user)**

Start the dev server and open `/fundingrequests/list/`:

- [ ] At ~1450px: docked sidebar on the right, no toggle button, no × — identical to before this work
- [ ] Resize to ~1350px: sidebar leaves the flow, list widens to full width, "Filters" button appears in the toolbar
- [ ] Click "Filters": drawer slides in from the right (200ms), no scrim, list still visible on the left
- [ ] Change a filter with the drawer open: list updates live, count badge follows in both the toolbar button and the drawer header
- [ ] × and Esc both close the drawer; the toggle button also toggles when reachable
- [ ] Search box and sort still work while the drawer is open
- [ ] Resize back above 1400px: docked sidebar returns, toggle/× disappear
- [ ] Reload with active filter params (e.g. append `?processing_status=approved`): drawer closed, "Filters (n)" badge shows the count
- [ ] Dark mode: drawer background, border/shadow, × and toggle colors are legible

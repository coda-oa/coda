# Funding Request Filter Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use skill tdd-reference for tests and production code.

**Goal:** Replace the flat "Advanced search" `<details>` filter form on `/fundingrequests/list/` with a persistent, always-visible filter sidebar (Status · Publication · Contract · Labels) plus a toolbar (live search + sort), with live HTMX filtering and no Search button.

**Architecture:** The view's GET-param contract is unchanged (all param names stay identical, so `fundingrequest_query.py`, pagination, label pills, and breadcrumb filter-preservation keep working). The page becomes a two-column layout: a sticky `<aside>` sidebar holding the filter controls (in a GET form) and a main column with the toolbar (search + sort, in a second GET form) and an HTMX list region that re-queries on form changes. **HTMX responses are partials:** the view returns only the list-region template (`fundingrequests/partials/fundingrequest_list_region.html`) when the `HX-Request` header is present — HTMX 2 would otherwise swap the whole `<body>` of a full-document response into the region (verified against HTMX 2.0.0 source/docs). The existing `search-select-multi` / `search-select` web components gain `change` event dispatch so HTMX can react to them.

**Tech Stack:** Django 5 templates (Pico.css), HTMX 2.0.0 (already loaded in `base.html`), vanilla JS web components, pytest + pytest-django. All commands run inside the dev container: `docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run <cmd>'`.

**Spec:** `docs/superpowers/specs/2026-09-01-funding-request-filter-sidebar-design.md`

**Notes for the worker:**

- Pre-commit runs on every commit (ruff, black, mypy --strict, djlint, commitizen). djlint may reformat HTML templates on commit — that is expected; re-run the commit if a hook auto-fixed files.
- Commit message style: `type(scope): summary` (commitizen validates).
- Never commit `.superpowers/` (brainstorm scratch dir).
- **Verified during planning, no action needed:** the spec's suspected `OpenAccessType` name/value bug is not a bug — the DB stores enum *names* (`publications.Publication.open_access_type` default `OpenAccessType.Closed.name`), the view parses GET values by enum *value* (`OpenAccessType(oat)`), and `OpenAccessTypeCriteria` queries by `.name`. The round-trip is correct for Opt-in/Opt-out.
- The old `status_dropdown.html` / `payment_method.html` checkbox dropdowns mis-detected multi-value selection (`status in request.GET.processing_status` — substring containment). They are retired in Task 6; the replacement `search-select-multi` partials use the `getlist` tag correctly, which resolves the bug.

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Modify | `src/coda/apps/static/js/search-select-multi.js` | Dispatch `change` on user select/deselect (Task 1) |
| Modify | `src/coda/apps/static/js/search-select.js` | Dispatch `change` on user selection (Task 1) |
| Modify | `src/coda/apps/fundingrequests/views/listview.py` | Add `filter_count` context; remove `expand_advanced_search` + `exlude_labels` typo (Tasks 2, 4) |
| Create | `src/coda/apps/templates/fundingrequests/fundingrequest_filter_sidebar.html` | Sidebar: header + 4 filter groups (Task 3) |
| Create | `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html` | Toolbar: search input + sort select (Task 3) |
| Modify | `src/coda/apps/templates/fundingrequests/fundingrequest_list.html` | Two-column layout, two GET forms, HTMX list region (Task 4) |
| Delete | `src/coda/apps/templates/fundingrequests/forms/fundingrequest_filter.html` | Old flat filter form (Task 6) |
| Delete | `src/coda/apps/templates/fundingrequests/forms/status_dropdown.html` | Old checkbox dropdown (Task 6) |
| Delete | `src/coda/apps/templates/fundingrequests/forms/payment_method.html` | Old checkbox dropdown (Task 6) |
| Delete | `src/coda/apps/templates/fundingrequests/forms/publication_type.html` | Old bare select (Task 6) |
| Modify | `src/coda/apps/static/css/fundingrequests.css` | Sidebar layout, segment control, header styles (Task 5) |
| Create | `tests/fundingrequests/test_fundingrequest_list_view.py` | View/template tests for the new UI (Tasks 2–4) |

**Kept and reused unchanged:** `forms/open_access_type_dropdown.html`, `forms/payment_status.html`, `forms/label_dropdown.html` (all `search-select-multi` based), `partials/pagination_nav.html`, `entity_list.html`, `fundingrequest_list_item.html`, `fundingrequest_query.py`.

---

### Task 1: Dispatch `change` events from the select web components

HTMX live filtering can only work if selecting a value in `search-select-multi` / `search-select` emits a bubbling `change` event. Neither component does this today (verified: no `dispatchEvent` calls in either file). There is no JS test runner in this repo, so this task is code change + manual verification.

**Files:**

- Modify: `src/coda/apps/static/js/search-select-multi.js` (class `SearchSelectMulti`, methods `selectOption` line 168, `removeSelectedOption` line 181)
- Modify: `src/coda/apps/static/js/search-select.js` (class `SearchSelect`, `searchResults` mousedown handler line 173, `searchBox` change handler line 192)

- [ ] **Step 1: Add change dispatch to `search-select-multi.js`**

Add a method to `class SearchSelectMulti` (next to `updateFormValue`, ~line 282):

```js
    dispatchChangeEvent() {
        this.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
    }
```

Call it at the end of `selectOption(optionText)` (after `this.hideDropdown();`) and at the end of `removeSelectedOption(optionValue)` (after `this.updateFormValue();`):

```js
    selectOption(optionText) {
        const optionElement = this.slotOptions.find(option => option.textContent.trim() === optionText);
        if (optionElement && optionElement.value) {
            const optionValue = optionElement.value;
            this.selectedOptions.set(optionValue, optionText);
            this.updateSelectedOptions();
            this.updateOriginalOptionElement(optionValue, true);
            this.updateFormValue();
            this.clearSearchInput();
            this.hideDropdown();
            this.dispatchChangeEvent();
        }
    }

    removeSelectedOption(optionValue) {
        this.selectedOptions.delete(optionValue);
        this.updateSelectedOptions();
        this.updateOriginalOptionElement(optionValue, false);
        this.updateFormValue();
        this.dispatchChangeEvent();
    }
```

Do NOT dispatch from `loadOptionsFromSlot()` / `connectedCallback` — that would fire a request on every page load.

- [ ] **Step 2: Add change dispatch to `search-select.js`**

Add a method to `class SearchSelect` (next to `resetFilter`, ~line 199):

```js
  dispatchChangeEvent() {
    this.dispatchEvent(new Event("change", { bubbles: true, composed: true }))
  }
```

Call it in the `searchResults` mousedown handler, after `this.searchResults.classList.remove("visible")`:

```js
    this.searchResults.addEventListener("mousedown", (e) => {
      if (e.target.tagName === 'LI') {
        this.searchBox.value = e.target.textContent.trim()
        this.setActiveElement(e.target, this.visibleItems.indexOf(e.target))
        this.setValueToActiveElementOrFirstMatch()
        this.searchResults.classList.remove("visible")
        this.dispatchChangeEvent()
      }
    })
```

And in the `searchBox` change handler, after `this.filterListItems()`:

```js
    this.searchBox.addEventListener("change", () => {
      this.setValueToActiveElementOrFirstMatch()
      this.filterListItems()
      this.dispatchChangeEvent()
    })
```

Do NOT dispatch from the `slotchange` handler (initialization path).

- [ ] **Step 3: Manual verification**

Start the dev server in the container (`docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run serve'` or the project's usual run command), open any page using these components (e.g. `/fundingrequests/list/`), open DevTools console, and run:

```js
document.addEventListener('change', e => console.log('change from', e.target.localName), true)
```

Pick an option in a `search-select-multi` and one in a `search-select` — each selection prints a `change` log. Load the page fresh — no log lines appear on load.

- [ ] **Step 4: Commit**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'git add src/coda/apps/static/js/search-select-multi.js src/coda/apps/static/js/search-select.js && git commit -m "feat(static/js): dispatch change events from search-select components"'
```

---

### Task 2: `filter_count` context variable

**Files:**

- Modify: `src/coda/apps/fundingrequests/views/listview.py`
- Test: `tests/fundingrequests/test_fundingrequest_list_view.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/fundingrequests/test_fundingrequest_list_view.py`:

```python
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import parse_html
from django.urls import reverse

from coda.contexts.fundingrequest.services.labels import label_create
from coda.domain.color import Color
from coda.domain.fundingrequest.review import ReviewResult


def get_list(client: Client, query: dict[str, Any] | None = None) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))


def selected_values(dom, name: str) -> list[str]:
    """Return the `selected` option values of the search-select-multi named `name`."""
    for element in dom.iter("search-select-multi"):
        if element.get("name") == name:
            return [o.get("value") for o in element.iter("option") if "selected" in o.attrib]
    raise AssertionError(f"no <search-select-multi name={name!r}> in page")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__filter_count_is_zero_without_filters(client: Client) -> None:
    response = get_list(client)

    assert response.context["filter_count"] == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__filter_count_counts_each_selected_value(client: Client) -> None:
    label = label_create("Counted Label", Color())

    response = get_list(
        client,
        {
            "processing_status": [ReviewResult.Approved.value, ReviewResult.Rejected.value],
            "labels": [label.pk],
            "publication_type": "article",
            "invalid_contract_years": "on",
        },
    )

    assert response.context["filter_count"] == 5


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__filter_count_ignores_default_publication_type(client: Client) -> None:
    response = get_list(client, {"publication_type": "all"})

    assert response.context["filter_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -v'
```

Expected: all 3 FAIL with `KeyError: 'filter_count'`.

- [ ] **Step 3: Implement `filter_count` in the view**

In `src/coda/apps/fundingrequests/views/listview.py`, add after the `_default_choices` definition (line 49):

```python
_multi_value_fields = (
    "labels",
    "exclude_labels",
    "processing_status",
    "open_access_type",
    "payment_status",
    "payment_methods",
)

_single_value_fields = (
    "start_date",
    "end_date",
    "contract_name",
    "contract_year",
    "invalid_contract_years",
)


def filter_count(request: HttpRequest) -> int:
    count = sum(len(request.GET.getlist(key)) for key in _multi_value_fields)
    count += sum(1 for key in _single_value_fields if request.GET.get(key))
    if request.GET.get("publication_type") not in (None, _default_choices["publication_type"]):
        count += 1
    return count
```

In `FundingRequestListView.get_context_data`, add the key to the returned dict (after `"payment_methods": payment_methods,`):

```python
            "filter_count": filter_count(self.request),
```

Leave `expand_advanced_search` and `exlude_labels` in place for now (removed in Task 4).

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -v'
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'git add tests/fundingrequests/test_fundingrequest_list_view.py src/coda/apps/fundingrequests/views/listview.py && git commit -m "feat(fundingrequests/listview): add filter_count to list view context"'
```

---

### Task 3: Sidebar and toolbar templates

**Files:**

- Create: `src/coda/apps/templates/fundingrequests/fundingrequest_filter_sidebar.html`
- Create: `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html`
- Modify: `src/coda/apps/fundingrequests/views/listview.py:78` (title-case publication type labels for the segment)
- Test: `tests/fundingrequests/test_fundingrequest_list_view.py` (append)

- [ ] **Step 1: Write the failing tests**

IMPORTANT: `django.test.html.parse_html` returns `Element` objects whose API is `name`, `attributes` (list of `(name, value)` tuples, boolean attrs have value `None`), `children` (mixed `Element` and `str` text nodes). There is NO `iter()`/`get()`/`attrib` — use the existing `_walk` helper from Task 2.

Append to `tests/fundingrequests/test_fundingrequest_list_view.py`:

```python
def checked_radio_values(dom: Element, name: str) -> list[str]:
    values: list[str] = []
    for element in _walk(dom):
        attrs = dict(element.attributes)
        if element.name == "input" and attrs.get("name") == name and "checked" in attrs:
            values.append(str(attrs.get("value", "")))
    return values


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__marks_selected_processing_statuses(client: Client) -> None:
    response = get_list(client, {"processing_status": ["approved", "rejected"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "processing_status") == ["approved", "rejected"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__marks_selected_payment_methods(client: Client) -> None:
    response = get_list(client, {"payment_methods": ["direct"]})

    dom = parse_html(response.content.decode())

    assert selected_values(dom, "payment_methods") == ["direct"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__marks_selected_publication_type(client: Client) -> None:
    response = get_list(client, {"publication_type": "monograph"})

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["monograph"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__sidebar__defaults_publication_type_to_all(client: Client) -> None:
    response = get_list(client)

    dom = parse_html(response.content.decode())

    assert checked_radio_values(dom, "publication_type") == ["all"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -v'
```

Expected: the 4 new tests FAIL (`no <search-select-multi name=...>` / no publication_type radios); the 3 from Task 2 still pass.

- [ ] **Step 3: Title-case the publication type labels in the view**

In `listview.py` `get_context_data`, change line 78:

```python
        publication_types = [(et.value, et.value.title()) for et in fq.PublicationEntityType]
```

(`"all".title()` → `"All"`, `"article".title()` → `"Article"`, `"monograph".title()` → `"Monograph"`.)

- [ ] **Step 4: Create the sidebar template**

Create `src/coda/apps/templates/fundingrequests/fundingrequest_filter_sidebar.html`:

```html
{% load getlist %}
<div class="filter-sidebar-header">
    <h2 class="filter-sidebar-title">
        Filters
        {% if filter_count %}<span class="filter-count">{{ filter_count }}</span>{% endif %}
    </h2>
    {% if filter_count %}
        <a href="{% url 'fundingrequests:list' %}" class="filter-clear">Clear all</a>
    {% endif %}
</div>

<div class="filter-group">
    <h3 class="filter-group-title">Status</h3>
    <div class="form-row">
        <label for="processing_status">Processing Status</label>
        <search-select-multi id="processing_status" name="processing_status" class="w-100">
        {% for status in processing_states %}
            <option slot="options"
                    value="{{ status }}"
                    {% if status in request.GET|getlist:"processing_status" %}selected{% endif %}>{{ status }}</option>
        {% endfor %}
        </search-select-multi>
    </div>
    {% include "fundingrequests/forms/payment_status.html" %}
    <div class="form-row">
        <label for="payment_methods">Payment Method</label>
        <search-select-multi id="payment_methods" name="payment_methods" class="w-100">
        {% for value, label in payment_methods %}
            <option slot="options"
                    value="{{ value }}"
                    {% if value in request.GET|getlist:"payment_methods" %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
        </search-select-multi>
    </div>
    {% include "fundingrequests/forms/open_access_type_dropdown.html" %}
</div>

<div class="filter-group">
    <h3 class="filter-group-title">Publication</h3>
    <div class="segment" role="radiogroup" aria-label="Publication type">
        {% for type in publication_types %}
            <input type="radio"
                   id="publication_type_{{ type.0 }}"
                   name="publication_type"
                   value="{{ type.0 }}"
                   {% if type.0 == selected_publication_types or not selected_publication_types and type.0 == "all" %}checked{% endif %}>
            <label for="publication_type_{{ type.0 }}">{{ type.1 }}</label>
        {% endfor %}
    </div>
    <div class="grid">
        <div class="form-row">
            <label for="id_start_date" class="form-row-item-sm">Start Date</label>
            <input type="date" id="id_start_date" name="start_date" value="{{ request.GET.start_date }}">
        </div>
        <div class="form-row">
            <label for="id_end_date" class="form-row-item-sm">End Date</label>
            <input type="date" id="id_end_date" name="end_date" value="{{ request.GET.end_date }}">
        </div>
    </div>
</div>

<div class="filter-group">
    <h3 class="filter-group-title">Contract</h3>
    <div class="form-row">
        <label for="contract_name">Contract</label>
        <search-select id="contract_name" name="contract_name" class="w-100">
        <li {% if not request.GET.contract_name %}selected{% endif %} value>-------</li>
        {% for contract in contract_list %}
            <li value="{{ contract.id }}"
                {% if contract.id|stringformat:"s" == request.GET.contract_name %}selected{% endif %}>
                {{ contract.name }}
            </li>
        {% endfor %}
        </search-select>
    </div>
    <div class="form-row">
        <label for="contract_year">Contract Year</label>
        <input type="text" id="contract_year" name="contract_year" value="{{ request.GET.contract_year }}">
    </div>
    <label class="filter-switch-row">
        <input type="checkbox"
               name="invalid_contract_years"
               id="invalid_contract_years"
               role="switch"
               {% if request.GET.invalid_contract_years %}checked aria-checked="true" {% else %}aria-checked="false" {% endif %}>
        Invalid contract years only
    </label>
</div>

<div class="filter-group">
    <h3 class="filter-group-title">Labels</h3>
    {% include "fundingrequests/forms/label_dropdown.html" %}
</div>
```

Notes:

- The three included partials (`payment_status.html`, `open_access_type_dropdown.html`, `label_dropdown.html`) already use `search-select-multi` + the `getlist` tag with the correct GET preselection — no changes to them.
- `label_dropdown.html` contains both "Labels" (include) and "Exclude labels" selects, matching the spec's Labels group.

- [ ] **Step 5: Create the toolbar template**

Create `src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html`:

```html
<div class="filter-toolbar">
    <input type="search"
           name="search_term"
           value="{{ request.GET.search_term }}"
           placeholder="Search by title, author, journal, publisher or ID"
           class="filter-search">
    <select name="sort_by" id="sort_by" class="filter-sort">
        <option value="date_desc"
                {% if request.GET.sort_by == "date_desc" %}selected{% endif %}>Date descending</option>
        <option value="date_asc"
                {% if request.GET.sort_by == "date_asc" %}selected{% endif %}>Date ascending</option>
        <option value="alphabetical"
                {% if request.GET.sort_by == "alphabetical" %}selected{% endif %}>Alphabet</option>
    </select>
</div>
```

- [ ] **Step 6: Wire the new layout into the list page**

The tests request the list page, so the new templates must be rendered. Update `src/coda/apps/templates/fundingrequests/fundingrequest_list.html` to the final layout now (done in this task rather than Task 4 so the tests can assert against it; Task 4 only adds lock-in tests and cleans the view):

```html
{% extends "base.html" %}
{% block content %}
    {% include "fundingrequests/fundingrequest_list_title_bar.html" with entity_name="Funding Requests" entity_create_url="fundingrequests:create_wizard" entity_secondary_create_url="fundingrequests:create_monograph" %}
    <div class="filter-layout">
        <aside class="filter-sidebar">
            <form method="get" id="filter-sidebar-form">
                {% include "fundingrequests/fundingrequest_filter_sidebar.html" %}
            </form>
        </aside>
        <div class="filter-main">
            <form method="get" id="filter-toolbar-form">
                {% include "fundingrequests/fundingrequest_filter_toolbar.html" %}
            </form>
            <div id="fundingrequest-list"
                 class="filter-list"
                 hx-get="{% url 'fundingrequests:list' %}"
                 hx-include="#filter-sidebar-form, #filter-toolbar-form"
                 hx-trigger="change from:#filter-sidebar-form, change from:#filter-toolbar-form, keyup delay:300ms from:#filter-toolbar-form">
                {% include "partials/pagination_nav.html" %}
                {% include "entity_list.html" with list_item_template="fundingrequests/fundingrequest_list_item.html" %}
                {% if request.GET and entities|length == 0 %}
                    <p class="my-2">No funding requests match the selected filters.
                        <a href="{% url 'fundingrequests:list' %}">Clear all filters</a>
                    </p>
                {% endif %}
                {% include "partials/pagination_nav.html" %}
            </div>
        </div>
    </div>
{% endblock content %}
```

Key points:

- Two separate GET forms (sidebar, toolbar). No form is nested in another — the pagination "jump to page" form lives inside the list region, outside both forms.
- The list region re-queries the same URL with `hx-trigger="change from:#filter-sidebar-form, change from:#filter-toolbar-form, keyup delay:300ms from:#filter-toolbar-form, submit from:#filter-toolbar-form"`. The `submit` trigger intercepts the search box's implicit form submission (without it, Enter in the search box would navigate the whole page and drop all sidebar filters).
- **The view returns a partial for HTMX requests** (`render_to_response` override: `HX-Request` header → render `fundingrequests/partials/fundingrequest_list_region.html` only; the page template includes that same partial inside the region div). This is required: HTMX 2 swaps the entire `<body>` of full-document responses into the target, which would duplicate the nav/forms/IDs.
- Full page loads without JS still work: the forms are plain GET forms (they just have no submit button; the pagination and pill links carry the params).

- [ ] **Step 7: Run tests to verify they pass**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -v'
```

Expected: all 7 passed.

- [ ] **Step 8: Commit**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'git add src/coda/apps/templates/fundingrequests/fundingrequest_filter_sidebar.html src/coda/apps/templates/fundingrequests/fundingrequest_filter_toolbar.html src/coda/apps/templates/fundingrequests/fundingrequest_list.html src/coda/apps/fundingrequests/views/listview.py tests/fundingrequests/test_fundingrequest_list_view.py && git commit -m "feat(fundingrequests/list): add filter sidebar and toolbar with HTMX list region"'
```

(djlint will reformat the templates in place during the commit; the commit succeeds with the formatted result.)

---

### Task 4: View cleanup + layout regression tests

**Files:**

- Modify: `src/coda/apps/fundingrequests/views/listview.py`
- Test: `tests/fundingrequests/test_fundingrequest_list_view.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundingrequests/test_fundingrequest_list_view.py` (use the `parse_html` `Element` API via the existing `_walk` helper — no `iter()`/`get()`/`attrib`):

```python
def attributes_of(dom: Element, id_value: str) -> dict[str, str | None]:
    for element in _walk(dom):
        attrs = dict(element.attributes)
        if attrs.get("id") == id_value:
            return attrs
    raise AssertionError(f"no element with id={id_value!r} in page")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_page__list_region_has_htmx_attributes(client: Client) -> None:
    response = get_list(client)

    region = attributes_of(parse_html(response.content.decode()), "fundingrequest-list")

    hx_get = str(region.get("hx-get") or "")
    hx_trigger = str(region.get("hx-trigger") or "")
    hx_include = str(region.get("hx-include") or "")

    assert hx_get.endswith("/fundingrequests/list/")
    assert "change from:#filter-sidebar-form" in hx_trigger
    assert "keyup delay:300ms from:#filter-toolbar-form" in hx_trigger
    assert "#filter-sidebar-form" in hx_include
    assert "#filter-toolbar-form" in hx_include


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_page__old_flat_filter_form_is_gone(client: Client) -> None:
    response = get_list(client)

    dom = parse_html(response.content.decode())
    form_ids = [str(dict(e.attributes).get("id") or "") for e in _walk(dom) if e.name == "form"]

    assert "search-form" not in form_ids
    assert "filter-sidebar-form" in form_ids
    assert "filter-toolbar-form" in form_ids
```

- [ ] **Step 2: Run tests to verify they pass already (layout exists since Task 3)**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_list_view.py -v'
```

Expected: all 9 passed. (These lock in the Task 3 layout; they would catch accidental regressions.)

- [ ] **Step 3: Remove dead context from the view**

In `src/coda/apps/fundingrequests/views/listview.py`:

1. Delete the `_advanced_search_fields` list (lines 22–33) — replaced by `_multi_value_fields` / `_single_value_fields` from Task 2.
2. In `get_context_data`, delete these lines:

```python
        expand_advanced_search = any(
            self.request.GET.get(key)
            for key in _advanced_search_fields
            if self.request.GET.get(key) and self.request.GET.get(key) != _default_choices.get(key)
        )
```

3. In the returned dict, delete:

```python
            "exlude_labels": labels,
            "expand_advanced_search": expand_advanced_search,
```

(The template used `labels` for both selects, so `exlude_labels` was already dead. No template references `expand_advanced_search` anymore.)

- [ ] **Step 4: Verify nothing else references the removed names**

```bash
grep -rn "expand_advanced_search\|exlude_labels\|_advanced_search_fields" src/ tests/
```

Expected: no matches.

- [ ] **Step 5: Run the search regression suite + new tests**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run pytest tests/fundingrequests/test_fundingrequest_search.py tests/fundingrequests/test_fundingrequest_list_view.py -v'
```

Expected: all passed (the search tests prove the query-param contract is intact).

- [ ] **Step 6: Type check and lint**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run mypy && pdm run ruff check .'
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'git add src/coda/apps/fundingrequests/views/listview.py tests/fundingrequests/test_fundingrequest_list_view.py && git commit -m "refactor(fundingrequests/listview): drop dead advanced-search context"'
```

---

### Task 5: CSS for the sidebar layout

**Files:**

- Modify: `src/coda/apps/static/css/fundingrequests.css` (append)

No automated CSS tests — verify manually in the browser.

- [ ] **Step 1: Append the styles**

Append to `src/coda/apps/static/css/fundingrequests.css` (uses existing variables from `vars.css`):

```css
/* Funding request list: filter sidebar layout */
.filter-layout {
    display: flex;
    gap: var(--pico-spacing, 1rem);
    align-items: flex-start;
}

.filter-sidebar {
    width: 250px;
    flex-shrink: 0;
    position: sticky;
    top: 1rem;
    max-height: calc(100vh - 2rem);
    overflow-y: auto;
}

.filter-main {
    flex: 1;
    min-width: 0;
}

.filter-list {
    margin-top: 0.5rem;
}

/* Toolbar */
.filter-toolbar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.5rem;
}

.filter-search {
    flex: 1;
}

.filter-sort {
    width: auto;
}

/* Sidebar header */
.filter-sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.75rem;
}

.filter-sidebar-title {
    margin: 0;
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

.filter-count {
    display: inline-block;
    min-width: 1.4em;
    padding: 0.1em 0.5em;
    border-radius: var(--coda-pill-border-radius);
    background: var(--coda-primary);
    color: var(--pico-color-inverse, #fff);
    font-size: 0.75rem;
    text-align: center;
}

.filter-clear {
    font-size: 0.8rem;
}

/* Groups */
.filter-group {
    margin-bottom: 1.25rem;
}

.filter-group-title {
    margin: 0 0 0.5rem;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--pico-muted-color);
    border-bottom: 1px solid var(--coda-muted-border-color);
    padding-bottom: 0.25rem;
}

.filter-group .form-row {
    margin-bottom: 0.5rem;
}

.filter-switch-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
}

/* Publication type segment */
.segment {
    display: inline-flex;
    border: var(--coda-border-width) solid var(--coda-border-color);
    border-radius: var(--coda-border-radius);
    overflow: hidden;
    margin-bottom: 0.5rem;
}

.segment input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
}

.segment label {
    padding: var(--coda-form-element-spacing-vertical) var(--coda-form-element-spacing-horizontal);
    font-size: 0.85rem;
    cursor: pointer;
    color: var(--pico-color);
    background: var(--coda-form-element-background-color);
}

.segment label:hover {
    background: var(--pico-primary-background);
}

.segment input:checked + label {
    background: var(--coda-primary);
    color: var(--pico-color-inverse, #fff);
}

.segment input:focus-visible + label {
    outline: 2px solid var(--coda-primary);
    outline-offset: -2px;
}
```

- [ ] **Step 2: Manual verification in the browser**

Run the dev server, open `/fundingrequests/list/` with some data, and check:

- Sidebar is fixed ~250 px on the left, sticky while scrolling a long list; list takes the remaining width.
- Groups are visually separated by the uppercase titles; the filter count badge and "Clear all" appear only when filters are active.
- The segment control highlights the checked option; the hidden radios are keyboard-focusable (Tab → visible outline).
- The list rows do not overflow the main column (long titles truncate/ellipsize as before).

- [ ] **Step 3: Commit**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'git add src/coda/apps/static/css/fundingrequests.css && git commit -m "style(fundingrequests/list): add filter sidebar and segment control styles"'
```

---

### Task 6: Delete the old filter templates

**Files:**

- Delete: `src/coda/apps/templates/fundingrequests/forms/fundingrequest_filter.html`
- Delete: `src/coda/apps/templates/fundingrequests/forms/status_dropdown.html`
- Delete: `src/coda/apps/templates/fundingrequests/forms/payment_method.html`
- Delete: `src/coda/apps/templates/fundingrequests/forms/publication_type.html`

- [ ] **Step 1: Verify nothing references them**

```bash
grep -rn "fundingrequest_filter.html\|status_dropdown\|forms/payment_method\|forms/publication_type" src/coda/ tests/
```

Expected: no matches. (If any match appears, stop and fix the reference first.)

- [ ] **Step 2: Delete the files**

```bash
git rm src/coda/apps/templates/fundingrequests/forms/fundingrequest_filter.html \
       src/coda/apps/templates/fundingrequests/forms/status_dropdown.html \
       src/coda/apps/templates/fundingrequests/forms/payment_method.html \
       src/coda/apps/templates/fundingrequests/forms/publication_type.html
```

(Run on the host or in the container — the working tree is shared.)

- [ ] **Step 3: Run the full unit test suite**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run unittests'
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'git commit -m "refactor(fundingrequests/list): remove obsolete flat filter templates"'
```

---

### Task 7: Full verification

- [ ] **Step 1: Full test suite**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run unittests'
```

Expected: all pass.

- [ ] **Step 2: Lint, format check, type check**

```bash
docker exec -u dev-user -w /app coda_local_django bash -lc 'pdm run ruff check . && pdm run mypy'
```

Expected: clean.

- [ ] **Step 3: Manual UX checklist** (dev server running)

On `/fundingrequests/list/`:

- [ ] Type in the search box — list updates after ~300 ms without a full reload; clearing the box restores the list.
- [ ] Add a processing status chip — list updates immediately; the "Filters" badge increments.
- [ ] Remove a chip via its × — list updates; badge decrements; at 0 the badge and "Clear all" disappear.
- [ ] Pick a payment status, an open access type, and an include label — all combine (AND), list narrows each time.
- [ ] Exclude a label that is also included — backend semantics unchanged (exclude wins via `~Q`).
- [ ] Switch publication type via the segment — list updates.
- [ ] Set date range — list updates when a date input is committed.
- [ ] Pick a contract + contract year + "invalid contract years only" — list narrows.
- [ ] Change sort — list re-orders.
- [ ] "Clear all" — page resets to unfiltered.
- [ ] Paginate with active filters — filter params survive; jump-to-page works.
- [ ] Click a label pill / type icon on a row — filters apply; open a row and go back via breadcrumb — filters preserved.
- [ ] Reload the page with active filters — sidebar shows the selected values (server-rendered preselection).
- [ ] With zero matches: the "No funding requests match the selected filters." message shows with a working "Clear all filters" link.

- [ ] **Step 4: Stop the brainstorm server (cleanup)**

```bash
/Users/marcus/.cache/opencode/packages/superpowers@git+https:/github.com/obra/superpowers.git/node_modules/superpowers/skills/brainstorming/scripts/stop-server.sh /Users/marcus/Projects/coda/.superpowers/brainstorm/19854-1788279649
```

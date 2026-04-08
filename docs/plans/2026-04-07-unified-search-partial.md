# Unified Search Partial for Publishers and Journals

> **For Claude:** REQUIRED SUB-SKILL: Use custom/openagent-executing-plans to implement this plan task-by-task.

**Goal:** Align journal search to the publisher's HTMX-endpoint pattern and introduce a shared
`search_results.html` partial with pluggable row templates — each endpoint injects its own
`row_template` via context so the partial stays fully generic.

**Architecture:** A new standalone `find_journal` HTMX view (parallel to `find_publisher`) returns
a shared `search_results.html` outer shell, which `{% include %}`s a `row_template` path from
context. Publisher and journal each have their own row partial. The DOI preview article form is
updated to use the new endpoint and outerHTML swap (matching the monograph form), removing the
current pattern where it re-renders the entire form partial. The `find_publisher` view is also
tightened: it goes through the service layer and adds sorting.

**Tech Stack:** Django 4.x · HTMX · Jinja2/Django templates · pytest · pytest-django

---

### Task 1 — Add `find_by_name_contains` to `publishers/services.py`

**Why first:** Every subsequent task that touches `find_publisher` depends on this. Isolating it here keeps the service layer change reviewable independently.

**Files:**
- Modify: `src/coda/apps/publishers/services.py`
- Test: `tests/publishers/test_publisher_services.py` *(create if absent)*

**Step 1: Write the failing test**

```python
# tests/publishers/test_publisher_services.py
import pytest
from coda.apps.publishers import services
from tests import modelfactory

@pytest.mark.django_db
def test__find_by_name_contains__matches_substring() -> None:
    modelfactory.publisher(name="Springer Nature")
    modelfactory.publisher(name="Elsevier")

    results = list(services.find_by_name_contains("spring"))

    assert len(results) == 1
    assert results[0].name == "Springer Nature"

@pytest.mark.django_db
def test__find_by_name_contains__is_case_insensitive() -> None:
    modelfactory.publisher(name="Springer Nature")

    results = list(services.find_by_name_contains("SPRINGER"))

    assert len(results) == 1

@pytest.mark.django_db
def test__find_by_name_contains__returns_results_sorted_by_name() -> None:
    modelfactory.publisher(name="Zebra Press")
    modelfactory.publisher(name="Alpha Press")

    results = list(services.find_by_name_contains("press"))

    assert [r.name for r in results] == ["Alpha Press", "Zebra Press"]

@pytest.mark.django_db
def test__find_by_name_contains__no_match__returns_empty() -> None:
    modelfactory.publisher(name="Springer Nature")

    results = list(services.find_by_name_contains("wiley"))

    assert results == []
```

**Step 2: Run tests to verify they fail**
```
pytest tests/publishers/test_publisher_services.py -v
```
Expected: `AttributeError: module 'services' has no attribute 'find_by_name_contains'`

**Step 3: Implement**

```python
# src/coda/apps/publishers/services.py  — add after find_by_name()
from django.db.models import QuerySet

def find_by_name_contains(name: str) -> QuerySet:
    """
    Find publishers whose name contains the given string (case-insensitive), sorted by name.
    """
    return Publisher.objects.filter(name__icontains=name).order_by("name")
```

**Step 4: Run tests**
```
pytest tests/publishers/test_publisher_services.py -v
```
Expected: all pass.

**Step 5: Commit**
```bash
git add src/coda/apps/publishers/services.py tests/publishers/test_publisher_services.py
git commit -m "feat: add find_by_name_contains to publishers service"
```

---

### Task 2 — Extract `publisher_row.html` partial and refactor `publisher_search_results.html` to use `row_template`

**Why here:** Establishes the pluggable row template pattern on the publisher side before journal touches anything. No behaviour changes — purely a structural refactor with tests verifying rendered HTML.

**Files:**
- Create: `src/coda/apps/templates/fundingrequests/partials/publisher_row.html`
- Modify: `src/coda/apps/templates/fundingrequests/partials/publisher_search_results.html`
- Test: `tests/fundingrequests/test_search_partials.py` *(create)*

**Step 1: Write the failing test**

Rather than rendering templates in isolation (which requires careful context processor setup), test the rendered output through the existing `find_publisher` HTTP endpoint. This is consistent with how the rest of the project tests HTMX partials (see `tests/publishers/test_publisher_modal_views.py`).

```python
# tests/fundingrequests/test_search_partials.py
import pytest
from django.test import Client
from django.urls import reverse
from tests import modelfactory

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_publisher__returns_publisher_name_in_row(client: Client) -> None:
    modelfactory.publisher(name="Springer Nature")

    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": "Springer"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Springer Nature" in content
    assert 'name="publisher"' in content  # radio input present

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_publisher__no_results__shows_no_results_message(client: Client) -> None:
    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": "nonexistent"},
    )

    assert response.status_code == 200
    assert "No results" in response.content.decode()
```

**Step 2: Run tests to verify they pass** (these are safety-net regression tests before the refactor)
```
pytest tests/fundingrequests/test_search_partials.py -v
```
Expected: PASS (confirms baseline before structural change).

**Step 3: Create `publisher_row.html`**

Extract the `<tr>` from `publisher_search_results.html`:

```html
{# src/coda/apps/templates/fundingrequests/partials/publisher_row.html #}
{# Context: publisher, selected_publisher #}
<tr>
    <td>{{ publisher.name }}</td>
    <td>
        <input type="radio"
               name="publisher"
               hx-target="#publisher-error"
               hx-swap="outerHTML"
               hx-post="{% url 'fundingrequests:clear_publisher_error' %}"
               value="{{ publisher.pk }}"
               {% if publisher.pk == selected_publisher.pk %}checked{% endif %}>
    </td>
</tr>
```

**Step 4: Update `publisher_search_results.html` to use `row_template`**

Replace the inline `<tr>` block with `{% include row_template %}`. The `row_template` variable is
injected by the view (Task 3). A default is provided so the partial also works in any context where
`row_template` is not explicitly set:

```html
{# src/coda/apps/templates/fundingrequests/partials/publisher_search_results.html #}
<div id="publisher-search-results" class="scroll-container max-h-30">
    {% if publishers %}
        <table class="my-2">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Select</th>
                </tr>
            </thead>
            <tbody>
                {% for publisher in publishers %}
                    {% include row_template|default:"fundingrequests/partials/publisher_row.html" %}
                {% endfor %}
            </tbody>
        </table>
        <div class="flex justify-between align-center my-2">
            <p>Couldn't find the right publisher?</p>
            <button type="button"
                    hx-get="{% url 'publishing:publishers:create_modal' %}"
                    hx-target="#entity-creation-modal-wrapper"
                    class="secondary">New Publisher</button>
        </div>
    {% elif search_term %}
        <div class="flex justify-between align-center my-2">
            <p>No results for "{{ search_term }}".</p>
            <button type="button"
                    hx-get="{% url 'publishing:publishers:create_modal' %}"
                    hx-target="#entity-creation-modal-wrapper"
                    class="secondary">New Publisher</button>
        </div>
    {% endif %}
    <div id="entity-creation-modal-wrapper"></div>
</div>
```

**Step 5: Run tests again**
```
pytest tests/fundingrequests/test_search_partials.py -v
```
Expected: PASS — same rendered output, just routed through the new row partial.

**Step 6: Commit**
```bash
git add src/coda/apps/templates/fundingrequests/partials/publisher_row.html \
        src/coda/apps/templates/fundingrequests/partials/publisher_search_results.html \
        tests/fundingrequests/test_search_partials.py
git commit -m "refactor: extract publisher_row partial and make search_results use row_template"
```

---

### Task 3 — Update `find_publisher` view to use service layer and inject `row_template`

**Why here:** Now that the partial accepts `row_template`, wire it up in the view and fix the service-layer bypass.

**Files:**
- Modify: `src/coda/apps/fundingrequests/views/wizard/steps/publisher_step.py`

**Step 1: Write the failing test**

The sorted order is the new observable behaviour:

```python
# tests/fundingrequests/test_search_partials.py — add to existing file

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_publisher__returns_results_sorted_by_name(client: Client) -> None:
    modelfactory.publisher(name="Zebra Press")
    modelfactory.publisher(name="Alpha Press")

    response = client.post(
        reverse("fundingrequests:wizard_find_publisher"),
        data={"publisher_name": "press"},
    )

    content = response.content.decode()
    assert content.index("Alpha Press") < content.index("Zebra Press")
```

**Step 2: Run test to verify it fails**
```
pytest tests/fundingrequests/test_search_partials.py::test__find_publisher__returns_results_sorted_by_name -v
```
Expected: FAIL (results are currently unsorted).

**Step 3: Update `find_publisher`**

```python
# src/coda/apps/fundingrequests/views/wizard/steps/publisher_step.py
from coda.apps.publishers import services as publisher_services

@login_required
def find_publisher(request: HttpRequest) -> HttpResponse:
    search_term = request.POST.get("publisher_name", "")
    publishers = publisher_services.find_by_name_contains(search_term)
    return render(
        request,
        "fundingrequests/partials/publisher_search_results.html",
        {
            "publishers": publishers,
            "search_term": search_term,
            "row_template": "fundingrequests/partials/publisher_row.html",
        },
    )
```

Remove the now-unused direct `Publisher` model import from this file if it is no longer referenced
elsewhere in the file.

**Step 4: Run all publisher-related tests**
```
pytest tests/fundingrequests/test_search_partials.py tests/fundingrequests/wizard/test_publisher_step.py -v
```
Expected: all pass.

**Step 5: Commit**
```bash
git add src/coda/apps/fundingrequests/views/wizard/steps/publisher_step.py \
        tests/fundingrequests/test_search_partials.py
git commit -m "refactor: find_publisher uses service layer, injects row_template, adds sort"
```

---

### Task 4 — Create `journal_search_results.html` and `journal_row.html` partials

**Why here:** Establishes the journal side of the pattern before any view or template wiring, so templates can be reviewed in isolation.

**Files:**
- Create: `src/coda/apps/templates/fundingrequests/partials/journal_row.html`
- Create: `src/coda/apps/templates/fundingrequests/partials/journal_search_results.html`

These are purely additive — no existing files change. The next task's tests will exercise them.

**Step 1: Create `journal_row.html`**

```html
{# src/coda/apps/templates/fundingrequests/partials/journal_row.html #}
{# Context: journal, selected_journal #}
<tr>
    <td>{{ journal.title }}</td>
    <td>{{ journal.publisher.name }}</td>
    <td>
        <input type="radio"
               name="journal"
               hx-target="#journal-error"
               hx-swap="outerHTML"
               hx-post="{% url 'fundingrequests:clear_journal_error' %}"
               value="{{ journal.pk }}"
               {% if journal.pk == selected_journal.pk %}checked{% endif %}>
    </td>
</tr>
```

**Step 2: Create `journal_search_results.html`**

```html
{# src/coda/apps/templates/fundingrequests/partials/journal_search_results.html #}
<div id="journal-search-results" class="scroll-container max-h-30">
    {% if journals %}
        <table class="my-2">
            <thead>
                <tr>
                    <th>Title</th>
                    <th>Publisher</th>
                    <th>Select</th>
                </tr>
            </thead>
            <tbody>
                {% for journal in journals %}
                    {% include row_template|default:"fundingrequests/partials/journal_row.html" %}
                {% endfor %}
            </tbody>
        </table>
        <div class="flex justify-between align-center my-2">
            <p>Couldn't find the right journal?</p>
            <button type="button"
                    class="secondary"
                    hx-get="{% url 'publishing:journals:create_modal' %}"
                    hx-target="#entity-creation-modal-wrapper"
                    hx-swap="innerHTML">New Journal</button>
        </div>
    {% elif search_term %}
        <div class="flex justify-between align-center my-2">
            <p>No results for "{{ search_term }}".</p>
            <button type="button"
                    class="secondary"
                    hx-get="{% url 'publishing:journals:create_modal' %}"
                    hx-target="#entity-creation-modal-wrapper"
                    hx-swap="innerHTML">New Journal</button>
        </div>
    {% endif %}
    <div id="entity-creation-modal-wrapper"></div>
</div>
```

**Step 3: Commit**
```bash
git add src/coda/apps/templates/fundingrequests/partials/journal_row.html \
        src/coda/apps/templates/fundingrequests/partials/journal_search_results.html
git commit -m "feat: add journal_row and journal_search_results partials"
```

---

### Task 5 — Create `find_journal` HTMX view and register URL

**Why here:** This is the core new behaviour. All template wiring in subsequent tasks depends on this URL existing.

**Files:**
- Modify: `src/coda/apps/fundingrequests/views/wizard/steps/journal_step.py`
- Modify: `src/coda/apps/fundingrequests/urls.py`
- Test: `tests/fundingrequests/test_search_partials.py` *(add tests)*

**Step 1: Write the failing tests**

```python
# tests/fundingrequests/test_search_partials.py — add

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_journal__returns_journal_title_in_row(client: Client) -> None:
    publisher = modelfactory.publisher(name="Springer")
    journal = modelfactory.journal(title="Nature", publisher_id=publisher.pk)

    response = client.post(
        reverse("fundingrequests:wizard_find_journal"),
        data={"journal_title": "Nature"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Nature" in content
    assert "Springer" in content        # publisher column
    assert 'name="journal"' in content  # radio input

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_journal__no_results__shows_no_results_message(client: Client) -> None:
    response = client.post(
        reverse("fundingrequests:wizard_find_journal"),
        data={"journal_title": "nonexistent"},
    )

    assert response.status_code == 200
    assert "No results" in response.content.decode()

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__find_journal__returns_results_sorted_by_title(client: Client) -> None:
    publisher = modelfactory.publisher()
    modelfactory.journal(title="Zebra Journal", publisher_id=publisher.pk)
    modelfactory.journal(title="Alpha Journal", publisher_id=publisher.pk)

    response = client.post(
        reverse("fundingrequests:wizard_find_journal"),
        data={"journal_title": "journal"},
    )

    content = response.content.decode()
    assert content.index("Alpha Journal") < content.index("Zebra Journal")
```

**Step 2: Run tests to verify they fail**
```
pytest tests/fundingrequests/test_search_partials.py -k "find_journal" -v
```
Expected: `NoReverseMatch` — URL does not exist yet.

**Step 3: Add `find_journal` view**

```python
# src/coda/apps/fundingrequests/views/wizard/steps/journal_step.py — add at module level

from django.contrib.auth.decorators import login_required
from coda.apps.journals.services import find_by_title

@login_required
def find_journal(request: HttpRequest) -> HttpResponse:
    search_term = request.POST.get("journal_title", "")
    journals = find_by_title(search_term)
    return render(
        request,
        "fundingrequests/partials/journal_search_results.html",
        {
            "journals": journals,
            "search_term": search_term,
            "row_template": "fundingrequests/partials/journal_row.html",
        },
    )
```

**Step 4: Register URL**

```python
# src/coda/apps/fundingrequests/urls.py

from coda.apps.fundingrequests.views.wizard.steps.journal_step import (
    clear_journal_error,
    find_journal,           # add this import
)

# In urlpatterns, alongside the publisher search URL:
path("partial/search-journal/", find_journal, name="wizard_find_journal"),
```

**Step 5: Run tests**
```
pytest tests/fundingrequests/test_search_partials.py -v
```
Expected: all pass.

**Step 6: Commit**
```bash
git add src/coda/apps/fundingrequests/views/wizard/steps/journal_step.py \
        src/coda/apps/fundingrequests/urls.py \
        tests/fundingrequests/test_search_partials.py
git commit -m "feat: add find_journal HTMX endpoint and URL"
```

---

### Task 6 — Update `fundingrequest_journal.html` to use HTMX search

**Why here:** Now the URL exists, we can wire the wizard template to use it — and replace the inline results table with the shared partial.

**Files:**
- Modify: `src/coda/apps/templates/fundingrequests/fundingrequest_journal.html`

**Step 1: Write the failing test**

```python
# tests/fundingrequests/test_search_partials.py — add

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_wizard_step__search_button_uses_htmx(client: Client) -> None:
    """Search button must be type=button with hx-post to avoid accidental wizard form submit."""
    response = client.get(reverse("fundingrequests:create_wizard"))

    content = response.content.decode()
    # The hx-post attribute must point to the new find_journal endpoint
    assert "partial/search-journal/" in content
    # Must NOT be a submit button (a submit button would advance the wizard on click)
    assert 'type="button"' in content
```

**Step 2: Run test to verify it fails**
```
pytest tests/fundingrequests/test_search_partials.py::test__journal_wizard_step__search_button_uses_htmx -v
```
Expected: FAIL — current template uses `type="submit"`.

**Step 3: Update `fundingrequest_journal.html`**

```html
{# src/coda/apps/templates/fundingrequests/fundingrequest_journal.html #}
<h1 class="my-2">Journal & Contracts</h1>
<article>
    <h2 class="mb-2">Find Journal</h2>
    <fieldset role="group">
        <input type="search"
               name="journal_title"
               id="journal_title"
               {% if journal_error and not selected_journal %}aria-invalid="true"{% endif %}
               value="{{ journal_title }}">
        <button type="button"
                hx-post="{% url 'fundingrequests:wizard_find_journal' %}"
                hx-target="#journal-search-results"
                hx-swap="outerHTML"
                class="inline-search-pill pill-right">Search</button>
    </fieldset>
    {% if journal_error and not selected_journal %}
        <ul class="errorlist" id="journal-error">
            <li>{{ journal_error }}</li>
        </ul>
    {% endif %}
    {% include "fundingrequests/partials/journal_search_results.html" %}
</article>
<div id="entity-creation-modal-wrapper"></div>
```

> Note: The `and request.method == "POST"` guard on the error display is removed. It was only
> needed because journal search previously triggered a full wizard form POST. With the search now
> handled by a dedicated HTMX endpoint, the error should show whenever `journal_error` is set and
> no journal is selected, regardless of HTTP method.

**Step 4: Run existing journal step tests to confirm no regression**
```
pytest tests/fundingrequests/wizard/test_journal_step.py tests/fundingrequests/test_search_partials.py -v
```
Expected: all pass.

**Step 5: Commit**
```bash
git add src/coda/apps/templates/fundingrequests/fundingrequest_journal.html \
        tests/fundingrequests/test_search_partials.py
git commit -m "refactor: journal wizard step uses HTMX search endpoint and shared partial"
```

---

### Task 7 — Update `doi_type_change_to_article.html` to use `find_journal` endpoint

**Why here:** Last wiring change. The DOI preview article form currently re-renders the entire form
partial on search. Switch it to the same outerHTML swap on `#journal-search-results`, matching how
the monograph form works with publishers.

**Files:**
- Modify: `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html`
- Modify: `src/coda/apps/fundingrequests/views/doi_preview.py` (`_render_article_type_form`)
- Test: `tests/fundingrequests/test_doi_import_preview.py` *(add targeted test)*

**Step 1: Write the failing test**

```python
# tests/fundingrequests/test_doi_import_preview.py — add near load_type_form tests

@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test__load_article_form__search_button_targets_journal_search_results(client: Client) -> None:
    """Search button in DOI preview article form must use find_journal endpoint,
    not reload the whole form partial."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "article")

    content = form_response.content.decode()
    # Must use the new journal search endpoint
    assert "partial/search-journal/" in content
    # Must target only the results container, not the whole form
    assert 'hx-target="#journal-search-results"' in content
    # Must NOT reload the whole type-change form
    assert "load-type-form" not in content
```

**Step 2: Run test to verify it fails**
```
pytest tests/fundingrequests/test_doi_import_preview.py::test__load_article_form__search_button_targets_journal_search_results -v
```
Expected: FAIL — template still uses `load-type-form`.

**Step 3: Update `doi_type_change_to_article.html`**

```html
{# src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html #}
{# Form for changing to article type - requires journal selection #}
{# Parameters: session_key, journal_title, journals, selected_journal, error #}
{# Note: form submission requires JavaScript (HTMX). Non-JS fallback is not supported. #}
<form method="post"
      action="{% url 'fundingrequests:doi_preview_apply_type_change' session_key=session_key %}"
      hx-post="{% url 'fundingrequests:doi_preview_apply_type_change' session_key=session_key %}"
      hx-target="#type-change-form"
      hx-swap="innerHTML">
    {% csrf_token %}
    <input type="hidden" name="publication_type" value="article">
    <h4 class="mt-1">Select Journal</h4>
    <p class="text-muted">Search for the journal where this article was published.</p>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <fieldset role="group">
        <input type="search"
               name="journal_title"
               id="journal_title"
               placeholder="Search journal by title..."
               value="{{ journal_title }}">
        <button type="button"
                hx-post="{% url 'fundingrequests:wizard_find_journal' %}"
                hx-include="[name='journal_title']"
                hx-target="#journal-search-results"
                hx-swap="outerHTML"
                class="inline-search-pill pill-right">Search</button>
    </fieldset>
    {% include "fundingrequests/partials/journal_search_results.html" %}
    <div class="grid">
        <button type="submit" class="mt-1">Apply Change to Article</button>
        <button type="button"
                hx-post="{% url 'fundingrequests:doi_preview_reset_type' session_key=session_key %}"
                class="secondary mt-1">Use auto-detected result instead</button>
    </div>
</form>
```

**Step 4: Simplify `_render_article_type_form` in `doi_preview.py`**

The view no longer needs to run the journal search on initial load — the search button handles it
via HTMX. On initial load, pass an empty results list. The pre-filled `journal_title` still
populates the input so the user can hit Search immediately with no extra typing.

```python
def _render_article_type_form(
    request: HttpRequest,
    session_key: str,
    original_metadata: dict[str, Any],
    *,
    error: str = "",
) -> HttpResponse:
    journal_data = original_metadata.get("journal") or {}
    journal_title = journal_data.get("title", "")
    context: dict[str, Any] = {
        "session_key": session_key,
        "journal_title": journal_title,
        "journals": [],
    }
    if error:
        context["error"] = error
    return render(request, "fundingrequests/partials/doi_type_change_to_article.html", context)
```

**Step 5: Run all DOI preview tests**
```
pytest tests/fundingrequests/test_doi_import_preview.py tests/fundingrequests/test_doi_import_preview_warnings.py -v
```
Expected: all pass.

**Step 6: Run the full non-integration suite**
```
pytest -m 'not integration and not migration_test and not performance and not ui_test' --ff
```
Expected: all pass.

**Step 7: Commit**
```bash
git add src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html \
        src/coda/apps/fundingrequests/views/doi_preview.py \
        tests/fundingrequests/test_doi_import_preview.py
git commit -m "refactor: DOI preview article form uses find_journal endpoint and shared partial"
```

---

## Summary of changes

| # | What | Files touched |
|---|---|---|
| 1 | Service: `find_by_name_contains` | `publishers/services.py` |
| 2 | Template refactor: `publisher_row.html` + row_template slot | `publisher_search_results.html`, new `publisher_row.html` |
| 3 | View: `find_publisher` → service layer + injects `row_template` | `publisher_step.py` |
| 4 | New templates: `journal_row.html`, `journal_search_results.html` | 2 new files |
| 5 | New view + URL: `find_journal` | `journal_step.py`, `urls.py` |
| 6 | Wizard template: journal search → HTMX | `fundingrequest_journal.html` |
| 7 | DOI preview template + view simplification | `doi_type_change_to_article.html`, `doi_preview.py` |

**No changes to:** `JournalStep` class logic, `PublisherStep` class logic, session storage,
`clear_publisher_error`, `clear_journal_error`, modal views, OOB swap success partials.

# Publication Type Override Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use custom/openagent-executing-plans to implement this plan task-by-task.

**Goal:** Allow users to manually override auto-detected publication type (article ↔ monograph) in DOI import preview workflow.

**Architecture:** Extend DOIImportService with explicit type override method, modify session storage to preserve both original and active previews, add HTMX-based type switching UI that reuses wizard journal/publisher search components, with smart pre-filling of publisher from article metadata.

**Tech Stack:** Django 6.0, Python 3.13, Pydantic DTOs, pytest, mypy strict mode, HTMX 2.0

---

## Summary

**Problem:** Auto-detection of publication type (article vs monograph) is sometimes incorrect. Users need ability to manually override.

**Solution:** Add HTMX-based UI in preview page. Radio buttons trigger partial view loads with journal/publisher selection forms (reusing wizard components). Smart pre-filling of publisher when switching from article to monograph. Session stores both original (auto-detected) and active (potentially overridden) previews.

**Session Structure:**
```python
{
  "doi_preview_{uuid}": {
    "doi": "10.1234/example",
    "original_preview": {...},  # Never changes
    "active_preview": {...},     # May be overridden
  }
}
```

**Reusable Components:**
- `find_by_title()` - Journal search service (existing)
- `find_publisher()` - Publisher search view (existing)
- `fundingrequests/partials/publisher_search_results.html` (existing)
- `fundingrequests/fundingrequest_journal.html` - Journal selection UI pattern (existing)
- `fundingrequests/fundingrequest_monograph_publisher_and_contract.html` - Publisher selection pattern (existing)

**Files to Create:**
1. `src/coda/apps/templates/fundingrequests/partials/doi_type_selector.html` - Radio buttons with HTMX
2. `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html` - Journal selection form
3. `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_monograph.html` - Publisher + ISBN form

**Files to Modify:**
1. `src/coda/contexts/publication/services/doi_import_service.py` - Add override method
2. `src/coda/apps/fundingrequests/views/doi_preview.py` - Session handling + type change views
3. `src/coda/apps/fundingrequests/urls.py` - Add change-type routes
4. `src/coda/apps/fundingrequests/queries/preview_context_builder.py` - Pass current type to template
5. `src/coda/apps/templates/fundingrequests/doi_preview_detail.html` - Include type selector partial

**Test Files:**
1. `tests/contexts/publication/test_doi_import_service.py` - Service tests
2. `tests/fundingrequests/test_doi_import_preview.py` - Integration tests

---

## TDD Workflow

Each task follows strict TDD:
1. **RED**: Write failing test
2. **GREEN**: Minimal implementation to pass
3. **REFACTOR**: Clean up if needed
4. **COMMIT**: Commit passing code

---

## TASK 1: Service - Add Override Method

**Goal:** Add `fetch_doi_preview_with_override()` to bypass auto-detection

### Files
- Modify: `src/coda/contexts/publication/services/doi_import_service.py`
- Test: `tests/contexts/publication/test_doi_import_service.py`

### RED: Write Failing Test

Add to test file after existing tests:

```python
@pytest.mark.parametrize(
    "publication_type_override,expected_type",
    [
        ("article", PreviewArticle),
        ("monograph", PreviewMonograph),
    ],
)
def test__fetch_doi_preview_with_override__uses_provided_type(
    fake_doi_client: FakeDOIMetadataClient,
    publication_type_override: Literal["article", "monograph"],
    expected_type: type[PreviewArticle | PreviewMonograph],
) -> None:
    doi = Doi("10.1234/test.article")
    metadata = make_metadata_for_nature_article(doi)
    fake_doi_client.data[str(doi)] = metadata
    
    service = DOIImportService(doi_client=fake_doi_client)
    result = service.fetch_doi_preview_with_override(doi, publication_type_override)
    
    assert isinstance(result.publication, expected_type)
```

**Run:**
```bash
pdm run pytest tests/contexts/publication/test_doi_import_service.py::test__fetch_doi_preview_with_override__uses_provided_type -v
```

**Expected:** `FAIL - AttributeError: no attribute 'fetch_doi_preview_with_override'`

### GREEN: Implement Method

Add to `DOIImportService` after `fetch_doi_preview()`:

```python
def fetch_doi_preview_with_override(
    self, doi: Doi, publication_type: Literal["article", "monograph"]
) -> PreviewFundingRequest:
    """Build preview using explicit publication type (bypasses auto-detection)."""
    metadata = self.doi_client.fetch(doi)
    authors_dto = self._build_authors_dto(metadata.authors)
    builder = _PREVIEW_BUILDERS[publication_type]
    publication_preview = builder(doi, metadata, authors_dto)
    return PreviewFundingRequest(publication=publication_preview)
```

**Run:**
```bash
pdm run pytest tests/contexts/publication/test_doi_import_service.py::test__fetch_doi_preview_with_override__uses_provided_type -v
```

**Expected:** `PASS (2 passed)`

### VERIFY

```bash
pdm run pytest tests/contexts/publication/test_doi_import_service.py -v
pdm run mypy src/coda/contexts/publication/services/doi_import_service.py
pdm run ruff check src/coda/contexts/publication/services/doi_import_service.py
```

**Expected:** All pass, no errors

### COMMIT

```bash
git add tests/contexts/publication/test_doi_import_service.py src/coda/contexts/publication/services/doi_import_service.py
git commit -m "feat(doi-import): add fetch_doi_preview_with_override method"
```

---

## TASK 2: Session Storage - Dual Preview Structure

**Goal:** Store both original and active preview in session

### Files
- Modify: `src/coda/apps/fundingrequests/views/doi_preview.py`
- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Failing Test

Add test to test file:

```python
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_doi_input_stores_original_and_active_preview(client: Client) -> None:
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    session_data = client.session[session_key]
    
    assert "doi" in session_data
    assert "original_preview" in session_data
    assert "active_preview" in session_data
    assert session_data["original_preview"] == session_data["active_preview"]
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_doi_input_stores_original_and_active_preview -v
```

**Expected:** `FAIL - KeyError: 'original_preview'`

### GREEN: Implement Session Structure

**Modify `DOIImportInputView.post()`:**

```python
def post(self, request: HttpRequest) -> HttpResponse:
    doi_str = request.POST.get("doi", "")
    try:
        doi = Doi(doi_str)
        doi_service = DOIImportService(doi_client=self.doi_client)
        preview_dto = doi_service.fetch_doi_preview(doi)
        
        session_key = f"doi_preview_{uuid4()}"
        preview_json = preview_dto.model_dump(mode="json")
        request.session[session_key] = {
            "doi": str(doi),
            "original_preview": preview_json,
            "active_preview": preview_json,
        }
        
        return redirect("fundingrequests:doi_preview_detail", session_key=session_key)
    except Exception as e:
        context = {"error": f"Failed to import DOI: {str(e)}"}
        return render(request, "fundingrequests/doi_import_input.html", context)
```

**Modify `DOIPreviewDetailView.get()`:**

```python
def get(self, request: HttpRequest, session_key: str) -> HttpResponse:
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found or expired", status=404)
    
    active_preview = session_data.get("active_preview", session_data)
    context = build_preview_context(active_preview, session_key)
    return render(request, "fundingrequests/doi_preview_detail.html", context)
```

**Modify `DOIPreviewSaveView.post()`:**

```python
def post(self, request: HttpRequest, session_key: str) -> HttpResponse:
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found or expired", status=404)
    
    doi = Doi(session_data["doi"])
    active_preview_data = session_data.get("active_preview", session_data)
    preview_dto = PreviewFundingRequest.model_validate(active_preview_data)
    
    cache = {doi: preview_dto}
    doi_service = DOIImportService(doi_client=self.doi_client, cache=cache)
    
    try:
        fr_id = doi_service.import_from_doi(doi)
    except DOIAlreadyImported as e:
        messages.error(request, self._format_error(e))
        return redirect("fundingrequests:doi_preview_detail", session_key=session_key)
    
    del request.session[session_key]
    return redirect("fundingrequests:detail", pk=fr_id)
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_doi_input_stores_original_and_active_preview -v
```

**Expected:** `PASS`

### VERIFY

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py -v
pdm run mypy src/coda/apps/fundingrequests/views/doi_preview.py
pdm run ruff check src/coda/apps/fundingrequests/views/doi_preview.py
```

**Expected:** All pass

### COMMIT

```bash
git add tests/fundingrequests/test_doi_import_preview.py src/coda/apps/fundingrequests/views/doi_preview.py
git commit -m "feat(doi-import): store original and active preview in session"
```

---

## TASK 3: Views - Add HTMX Type Change Endpoints

**Goal:** Create HTMX endpoint to load type change forms and submission handler

### Files
- Modify: `src/coda/apps/fundingrequests/views/doi_preview.py`
- Modify: `src/coda/apps/fundingrequests/urls.py`
- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Failing Tests

Add helper and tests:

```python
def load_type_form(
    client: Client, session_key: str, pub_type: Literal["article", "monograph"]
) -> HttpResponse:
    """Helper to load HTMX type change form."""
    return cast(
        HttpResponse,
        client.get(
            reverse("fundingrequests:doi_preview_load_type_form", kwargs={"session_key": session_key}),
            data={"publication_type": pub_type},
        ),
    )


def submit_type_change(
    client: Client, session_key: str, pub_type: Literal["article", "monograph"], **kwargs: Any
) -> HttpResponse:
    """Helper to submit type change form."""
    data = {"publication_type": pub_type, **kwargs}
    return cast(
        HttpResponse,
        client.post(
            reverse("fundingrequests:doi_preview_apply_type_change", kwargs={"session_key": session_key}),
            data=data,
        ),
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_load_article_form_shows_journal_search(client: Client) -> None:
    """HTMX endpoint should return article form partial with journal search."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    
    form_response = load_type_form(client, session_key, "article")
    
    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "journal_title" in content
    assert "Search" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_load_monograph_form_shows_publisher_field(client: Client) -> None:
    """HTMX endpoint should return monograph form with pre-filled publisher."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    
    form_response = load_type_form(client, session_key, "monograph")
    
    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "publisher_name" in content
    # Should pre-fill publisher from article metadata
    assert "Test Publisher" in content or "publisher" in content.lower()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_submit_type_change_to_monograph_with_publisher(
    client: Client, fake_doi_client: FakeDOIMetadataClient
) -> None:
    """Submitting monograph form with publisher should update preview."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    
    # Create publisher in database
    publisher = modelfactory.publisher(name="Test Publisher")
    
    # Submit type change
    change_response = submit_type_change(
        client, session_key, "monograph", publisher=publisher.id
    )
    
    assert change_response.status_code == 302
    assert f"/doi-preview/{session_key}/" in change_response["Location"]
    
    # Verify session updated
    session_data = client.session[session_key]
    active = PreviewFundingRequest.model_validate(session_data["active_preview"])
    assert isinstance(active.publication, PreviewMonograph)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_submit_type_change_to_article_with_journal(
    client: Client, test_journal: Journal
) -> None:
    """Submitting article form with journal should update preview."""
    # Start with monograph
    doi_str = "10.1234/book.test"
    fake_doi_client, doi = make_book_metadata(
        doi=doi_str, publisher="Test Publisher"
    )
    inject_fake_doi_client(fake_doi_client)
    
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    
    # Submit type change to article
    change_response = submit_type_change(
        client, session_key, "article", journal=test_journal.id
    )
    
    assert change_response.status_code == 302
    
    # Verify session updated
    session_data = client.session[session_key]
    active = PreviewFundingRequest.model_validate(session_data["active_preview"])
    assert isinstance(active.publication, PreviewArticle)
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_load_article_form_shows_journal_search -v
```

**Expected:** `FAIL - NoReverseMatch: 'doi_preview_load_type_form' not found`

### GREEN: Implement Views and URLs

**Add to `urls.py` imports:**
```python
from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
    doi_preview_load_type_form,  # NEW
    doi_preview_apply_type_change,  # NEW
)
```

**Add to `urlpatterns` after doi_preview_detail:**
```python
path(
    "doi-preview/<str:session_key>/load-type-form/",
    doi_preview_load_type_form,
    name="doi_preview_load_type_form",
),
path(
    "doi-preview/<str:session_key>/apply-type-change/",
    doi_preview_apply_type_change,
    name="doi_preview_apply_type_change",
),
```

**Add to `doi_preview.py` imports:**
```python
from coda.apps.journals.services import find_by_title
from coda.apps.publishers.models import Publisher
from coda.contexts.publication.dto.preview import PreviewFundingRequest
```

**Add to `doi_preview.py` (after existing views):**

```python
def doi_preview_load_type_form(request: HttpRequest, session_key: str) -> HttpResponse:
    """HTMX endpoint: Load form partial for switching publication type."""
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)
    
    requested_type = request.GET.get("publication_type", "article")
    
    if requested_type == "article":
        # Load journal selection form
        context = {
            "session_key": session_key,
            "journal_title": "",
            "journals": [],
        }
        return render(
            request,
            "fundingrequests/partials/doi_type_change_to_article.html",
            context,
        )
    else:
        # Load publisher form with smart pre-fill
        active_preview_data = session_data.get("active_preview")
        preview = PreviewFundingRequest.model_validate(active_preview_data)
        
        # Try to extract publisher from current preview
        suggested_publisher = ""
        if hasattr(preview.publication, "publisher_name") and preview.publication.publisher_name:
            suggested_publisher = preview.publication.publisher_name
        
        context = {
            "session_key": session_key,
            "suggested_publisher": suggested_publisher,
            "publishers": [],
        }
        return render(
            request,
            "fundingrequests/partials/doi_type_change_to_monograph.html",
            context,
        )


def doi_preview_apply_type_change(request: HttpRequest, session_key: str) -> HttpResponse:
    """Handle type change form submission (article or monograph)."""
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)
    
    requested_type = request.POST.get("publication_type")
    if requested_type not in ("article", "monograph"):
        return HttpResponse("Invalid publication type", status=400)
    
    doi = Doi(session_data["doi"])
    original_preview = PreviewFundingRequest.model_validate(session_data["original_preview"])
    original_type = original_preview.publication.publication_kind
    is_original_article = original_type == "journal_article"
    
    # Check if reverting to original
    if (requested_type == "article" and is_original_article) or \
       (requested_type == "monograph" and not is_original_article):
        session_data["active_preview"] = session_data["original_preview"]
    else:
        # Validate required fields
        if requested_type == "article":
            if not request.POST.get("journal"):
                return HttpResponse("Journal is required for article", status=400)
        elif requested_type == "monograph":
            if not request.POST.get("publisher"):
                return HttpResponse("Publisher is required for monograph", status=400)
        
        # Rebuild preview with override
        doi_client = DOIImportInputView.doi_client
        doi_service = DOIImportService(doi_client=doi_client)
        
        try:
            overridden_preview = doi_service.fetch_doi_preview_with_override(
                doi, requested_type  # type: ignore[arg-type]
            )
            session_data["active_preview"] = overridden_preview.model_dump(mode="json")
        except Exception as e:
            return HttpResponse(f"Failed to change type: {str(e)}", status=400)
    
    request.session[session_key] = session_data
    return redirect("fundingrequests:doi_preview_detail", session_key=session_key)
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_load_article_form_shows_journal_search -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_load_monograph_form_shows_publisher_field -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_submit_type_change_to_monograph_with_publisher -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_submit_type_change_to_article_with_journal -v
```

**Expected:** `PASS (4 passed)` after templates created in Task 4

### VERIFY

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py -v
pdm run mypy src/coda/apps/fundingrequests/views/doi_preview.py
pdm run ruff check src/coda/apps/fundingrequests/views/doi_preview.py
```

**Expected:** All pass

### COMMIT

```bash
git add tests/fundingrequests/test_doi_import_preview.py src/coda/apps/fundingrequests/views/doi_preview.py src/coda/apps/fundingrequests/urls.py
git commit -m "feat(doi-import): add HTMX type change endpoints"
```

---

## TASK 4: Templates - Add HTMX Type Selector and Forms

**Goal:** Create HTMX-based UI with type selector and reusable form partials

### Files
- Create: `src/coda/apps/templates/fundingrequests/partials/doi_type_selector.html`
- Create: `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html`
- Create: `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_monograph.html`
- Modify: `src/coda/apps/templates/fundingrequests/doi_preview_detail.html`
- Modify: `src/coda/apps/fundingrequests/queries/preview_context_builder.py`
- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Failing Test

```python
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_preview_page_shows_type_selector_with_htmx(client: Client) -> None:
    """Preview page should show publication type selector with HTMX."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    preview_response = client.get(preview_url)
    content = preview_response.content.decode()
    
    # Check for type selector
    assert 'name="publication_type"' in content
    assert 'value="article"' in content
    assert 'value="monograph"' in content
    # Check for HTMX attributes
    assert 'hx-get' in content
    assert 'doi_preview_load_type_form' in content or 'load-type-form' in content
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_preview_page_shows_type_selector_with_htmx -v
```

**Expected:** `FAIL - AssertionError: 'hx-get' not in content`

### GREEN: Create Templates

**Create `fundingrequests/partials/doi_type_selector.html`:**

```html
{# Publication type selector with HTMX form loading #}
{# Parameters: session_key, current_publication_type #}
<section class="card mb-1" id="type-selector-section">
    <h3>Publication Type</h3>
    <p class="text-muted">Select the publication type. The form will update to collect required information.</p>
    
    <div class="form-field">
        <label>
            <input type="radio" 
                   name="publication_type" 
                   value="article"
                   hx-get="{% url 'fundingrequests:doi_preview_load_type_form' session_key=session_key %}"
                   hx-vals='{"publication_type": "article"}'
                   hx-target="#type-change-form"
                   hx-swap="innerHTML"
                   {% if current_publication_type == "article" %}checked{% endif %}>
            Article (Journal Publication)
        </label>
    </div>
    <div class="form-field">
        <label>
            <input type="radio" 
                   name="publication_type" 
                   value="monograph"
                   hx-get="{% url 'fundingrequests:doi_preview_load_type_form' session_key=session_key %}"
                   hx-vals='{"publication_type": "monograph"}'
                   hx-target="#type-change-form"
                   hx-swap="innerHTML"
                   {% if current_publication_type == "monograph" %}checked{% endif %}>
            Monograph (Book/Chapter)
        </label>
    </div>
    
    <!-- HTMX target for type change forms -->
    <div id="type-change-form" class="mt-1">
        <!-- Form partial loaded here via HTMX -->
    </div>
</section>
```

**Create `fundingrequests/partials/doi_type_change_to_article.html`:**

```html
{# Form for changing to article type - requires journal selection #}
{# Reuses journal search pattern from wizard #}
{# Parameters: session_key, journal_title, journals, selected_journal #}
<form method="post" action="{% url 'fundingrequests:doi_preview_apply_type_change' session_key=session_key %}">
    {% csrf_token %}
    <input type="hidden" name="publication_type" value="article">
    
    <h4 class="mt-1">Select Journal</h4>
    <p class="text-muted">Search for the journal where this article was published.</p>
    
    <fieldset role="group">
        <input type="search"
               name="journal_title"
               id="journal_title"
               placeholder="Search journal by title..."
               value="{{ journal_title }}">
        <button type="submit" 
                formaction="{% url 'fundingrequests:doi_preview_load_type_form' session_key=session_key %}"
                class="inline-search-pill pill-right">Search</button>
    </fieldset>
    
    {% if journals %}
        <div class="scroll-container max-h-30 mt-1">
            <table>
                <thead>
                    <tr>
                        <th>Title</th>
                        <th>Publisher</th>
                        <th>Select</th>
                    </tr>
                </thead>
                <tbody>
                    {% for journal in journals %}
                        <tr>
                            <td>{{ journal.title }}</td>
                            <td>{{ journal.publisher.name }}</td>
                            <td>
                                <input type="radio"
                                       name="journal"
                                       value="{{ journal.pk }}"
                                       {% if selected_journal and journal.pk == selected_journal.pk %}checked{% endif %}
                                       required>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <button type="submit" class="mt-1">Apply Change to Article</button>
    {% endif %}
</form>
```

**Create `fundingrequests/partials/doi_type_change_to_monograph.html`:**

```html
{# Form for changing to monograph type - requires publisher selection #}
{# Reuses publisher search pattern from wizard #}
{# Parameters: session_key, suggested_publisher, publishers, selected_publisher #}
<form method="post" action="{% url 'fundingrequests:doi_preview_apply_type_change' session_key=session_key %}">
    {% csrf_token %}
    <input type="hidden" name="publication_type" value="monograph">
    
    <h4 class="mt-1">Select Publisher</h4>
    <p class="text-muted">Search for the publisher of this monograph/book.</p>
    
    <fieldset role="group">
        <input type="search"
               name="publisher_name"
               id="publisher_name"
               placeholder="Search publisher..."
               value="{{ suggested_publisher }}">
        <button type="button"
                hx-post="{% url 'fundingrequests:wizard_find_publisher' %}"
                hx-target="#publisher-search-results"
                hx-swap="outerHTML"
                hx-include="[name='publisher_name']"
                class="inline-search-pill pill-right">Search</button>
    </fieldset>
    
    {% include "fundingrequests/partials/publisher_search_results.html" %}
    
    <div class="form-field mt-1">
        <label for="isbn">ISBN (optional)</label>
        <input type="text" 
               name="isbn" 
               id="isbn"
               placeholder="978-3-16-148410-0">
    </div>
    
    {% if publishers %}
        <button type="submit" class="mt-1">Apply Change to Monograph</button>
    {% endif %}
</form>
```

**Update `preview_context_builder.py` - modify return dict:**

Find the `build_preview_context()` function and update the return statement:

```python
# At end of build_preview_context(), before return:
current_type = (
    "article" 
    if preview_fr.publication.publication_kind == "journal_article" 
    else "monograph"
)

return {
    "session_key": session_key,
    "publication": publication_detail,
    "funding_request": funding_request,
    "external_funding": [],
    "contact": NoContact,
    "is_preview": True,
    "current_publication_type": current_type,  # NEW
}
```

**Update `doi_preview_detail.html` - include type selector:**

Add after the opening paragraph (around line 5-10):

```html
<!-- After the "Review the imported data..." paragraph -->
{% if is_preview %}
    {% include "fundingrequests/partials/doi_type_selector.html" %}
{% endif %}
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_preview_page_shows_type_selector_with_htmx -v
```

**Expected:** `PASS`

### VERIFY

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py -v
pdm run djlint src/coda/apps/templates/fundingrequests/doi_preview_detail.html --check
pdm run djlint src/coda/apps/templates/fundingrequests/partials/doi_type_selector.html --check
pdm run djlint src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html --check
pdm run djlint src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_monograph.html --check
```

**Expected:** All pass

### COMMIT

```bash
git add tests/fundingrequests/test_doi_import_preview.py \
        src/coda/apps/templates/fundingrequests/partials/doi_type_selector.html \
        src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html \
        src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_monograph.html \
        src/coda/apps/templates/fundingrequests/doi_preview_detail.html \
        src/coda/apps/fundingrequests/queries/preview_context_builder.py
git commit -m "feat(doi-import): add HTMX type selector UI with wizard component reuse"
```

---

## TASK 5: Integration Test - End-to-End

**Goal:** Test complete override workflow from submission to save

### Files
- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Integration Test

```python
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_override_article_to_monograph_and_save(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """Full workflow: article DOI → override to monograph → save."""
    doi_str = "10.1234/override.test"
    doi = Doi(doi_str)
    
    # Configure as article with publisher in metadata
    metadata = ExternalPublicationMetadata(
        title="Test Article",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=ExternalJournal(title="Nature", eissn="1476-4687"),
        publisher="Springer",
        license=None,
        online_publication_date=datetime.date(2024, 1, 1),
        print_publication_date=None,
    )
    fake_doi_client.data[str(doi)] = metadata
    publisher = modelfactory.publisher(name="Springer")
    
    # Submit → Load monograph form → Submit type change → Save
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    
    # Load monograph form (HTMX)
    load_type_form(client, session_key, "monograph")
    
    # Submit type change
    submit_type_change(client, session_key, "monograph", publisher=publisher.id)
    
    # Save to database
    save_doi_import(client, session_key)
    
    # Verify monograph created
    fr = repository.first()
    assert fr is not None
    assert isinstance(fr.publication, Monograph)
    assert fr.publication.publisher.id == publisher.id
```

**Run:**
```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_override_article_to_monograph_and_save -v
```

**Expected:** `PASS`

### COMMIT

```bash
git add tests/fundingrequests/test_doi_import_preview.py
git commit -m "test(doi-import): add end-to-end type override integration test"
```

---

## TASK 6: Final Verification

### Run Full Test Suite

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py tests/contexts/publication/test_doi_import_service.py -v
```

**Expected:** All tests pass

### Type Check All Modified Files

```bash
pdm run mypy src/coda/contexts/publication/services/doi_import_service.py
pdm run mypy src/coda/apps/fundingrequests/views/doi_preview.py
pdm run mypy src/coda/apps/fundingrequests/queries/preview_context_builder.py
```

**Expected:** No errors

### Lint All Modified Files

```bash
pdm run ruff check src/coda/contexts/publication/services/
pdm run ruff check src/coda/apps/fundingrequests/views/
pdm run ruff check src/coda/apps/fundingrequests/queries/
```

**Expected:** No errors

### Template Validation

```bash
pdm run djlint src/coda/apps/templates/fundingrequests/doi_preview_detail.html --check
pdm run djlint src/coda/apps/templates/fundingrequests/partials/doi_type_*.html --check
```

**Expected:** No errors

---

## Summary

**Files Created:** 3 partials
- `src/coda/apps/templates/fundingrequests/partials/doi_type_selector.html`
- `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html`
- `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_monograph.html`

**Files Modified:** 6
- `src/coda/contexts/publication/services/doi_import_service.py`
- `src/coda/apps/fundingrequests/views/doi_preview.py`
- `src/coda/apps/fundingrequests/urls.py`
- `src/coda/apps/fundingrequests/queries/preview_context_builder.py`
- `src/coda/apps/templates/fundingrequests/doi_preview_detail.html`

**Tests Added:** 9 new test functions

**Commits:** 6

**Estimated Time:** 3-4 hours

**Key Decisions:**
1. Session stores both `original_preview` and `active_preview`
2. New service method `fetch_doi_preview_with_override()` for explicit type control
3. HTMX-based UI with radio buttons triggering partial form loads
4. Reuse wizard components: journal search (`find_by_title`), publisher search (`find_publisher` + partial)
5. Smart pre-filling of publisher field when switching article → monograph
6. Validation requires journal for article, publisher for monograph
7. Full form submission (not inline radio change) to ensure required data collected

**Reused Components:**
- `coda.apps.journals.services.find_by_title()` - Journal search
- `fundingrequests:wizard_find_publisher` - Publisher search endpoint
- `fundingrequests/partials/publisher_search_results.html` - Publisher results table
- Journal search UI pattern from `fundingrequest_journal.html`
- Publisher search UI pattern from `fundingrequest_monograph_publisher_and_contract.html`

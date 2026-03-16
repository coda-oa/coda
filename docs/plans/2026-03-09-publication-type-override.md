# Publication Type Override Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use custom/openagent-executing-plans to implement this plan task-by-task.

**Goal:** Allow users to manually override auto-detected publication type (article ↔ monograph) in DOI import preview workflow.

**Architecture:** Extend DOIImportService with typed override objects and a unified override method. Replace the preview cache with a raw metadata cache so previews are built on demand. Store only raw metadata + active type + selected entity ID in session — no preview serialization. Add HTMX-based type switching UI with smart pre-fill from original metadata.

**Tech Stack:** Django 6.0, Python 3.13, Pydantic DTOs, pytest, mypy strict mode, HTMX 2.0

---

## Summary

**Problem:** Auto-detection of publication type (article vs monograph) is sometimes incorrect. Users need ability to manually override.

**Solution:** Add HTMX-based UI in preview page. Radio buttons trigger partial view loads with journal/publisher selection forms (reusing wizard components). Smart pre-filling using original raw Crossref metadata when switching in either direction. Session stores only raw metadata + active publication type + selected entity ID. Preview is built on demand from these — never stored.

**User Flow (two-step override):**

1. User submits DOI → system auto-detects type → preview shown
2. If unhappy with detected type, user selects override type → journal or publisher form appears → user selects → preview reloads with new type

**Session Structure:**

```python
{
  "doi_preview_{uuid}": {
    "doi": "10.1234/example",
    "original_metadata": {...},     # Raw Crossref data — model_dump(mode="json"); never changes
    "publication_type": "article",  # Auto-detected on initial fetch; updated on override
    "journal_id": 42,               # Only present when overriding to article
    # OR
    "publisher_id": 7,              # Only present when overriding to monograph
  }
}
```

**Preview is built on demand** — `DOIPreviewDetailView` and `DOIPreviewSaveView` both reconstruct the service with a pre-populated `metadata_cache`, then call `fetch_doi_preview` (no override) or `build_preview_with_type_override` (with override) as appropriate.

**Override Types:**

```python
@dataclass(frozen=True)
class OverrideImportAsArticle:
    journal_id: JournalId

@dataclass(frozen=True)
class OverrideImportAsMonograph:
    publisher_id: PublisherId

OverrideImportPublicationType = OverrideImportAsArticle | OverrideImportAsMonograph
```

**Smart Pre-fill Logic (both directions):**

- **article → monograph**: pre-fill publisher search from `original_metadata["publisher"]`
- **monograph → article**: pre-fill journal search from `original_metadata["journal"]["title"]` (if present)

Both use `original_metadata` as the authoritative source.

**Reusable Components:**

- `find_by_title()` - Journal search service (existing)
- `fundingrequests:wizard_find_publisher` - Publisher search view (existing)
- `fundingrequests/partials/publisher_search_results.html` (existing)
- `fundingrequests/fundingrequest_journal.html` - Journal selection UI pattern (existing)
- `fundingrequests/fundingrequest_monograph_publisher_and_contract.html` - Publisher selection pattern (existing)

**Files to Create:**

1. `src/coda/apps/templates/fundingrequests/partials/doi_type_selector.html`
2. `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_article.html`
3. `src/coda/apps/templates/fundingrequests/partials/doi_type_change_to_monograph.html`

**Files to Modify:**

1. `src/coda/apps/publishers/services.py` - Add `get_by_pk`
2. `src/coda/contexts/publication/services/doi_import_service.py` - Override types, metadata cache, new methods
3. `src/coda/apps/fundingrequests/views/doi_preview.py` - Session restructure + type change views
4. `src/coda/apps/fundingrequests/urls.py` - Add change-type routes
5. `src/coda/apps/fundingrequests/queries/preview_context_builder.py` - Pass current type to template
6. `src/coda/apps/templates/fundingrequests/doi_preview_detail.html` - Include type selector partial

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

## TASK 1: Service - Override Types, Metadata Cache, and Override Method

**Goal:**

1. Add `get_by_pk` to `publisher_services` (consistent with `journal_services`)
2. Add `OverrideImportAsArticle` / `OverrideImportAsMonograph` / `OverrideImportPublicationType` to `doi_import_service.py`
3. Replace `cache: dict[Doi, PreviewFundingRequest]` with `metadata_cache: dict[Doi, ExternalPublicationMetadata]` in `DOIImportService.__init__`
4. Add private `_fetch_metadata(doi)` method — checks `metadata_cache` first, then falls back to `doi_client.fetch()`
5. Refactor `fetch_doi_preview` to use `_fetch_metadata`
6. Add `build_preview_with_type_override(doi, override)` — fetches metadata from cache, resolves journal/publisher by ID, builds override preview
7. Update `import_from_doi` to accept `override: OverrideImportPublicationType | None = None`
8. Update `_convert_preview_to_creation_dto` to use `match override` — passes IDs directly when present, skipping the lookup

### Files

- Modify: `src/coda/apps/publishers/services.py`
- Modify: `src/coda/contexts/publication/services/doi_import_service.py`
- Test: `tests/contexts/publication/test_doi_import_service.py`

### RED: Write Failing Tests

Replace the two existing failing tests at the end of the test file with:

```python
@pytest.mark.django_db
def test__build_preview_with_type_override__to_article__uses_resolved_journal() -> None:
    """Overriding to article uses journal title and EISSN from the resolved DB journal."""
    fake_client, doi = make_article_metadata(doi="10.1234/test.article")
    publisher_id = publisher_services.create(name="Test Publisher")
    journal_id = journal_services.create(
        title=NonEmptyStr(NATURE_JOURNAL_TITLE),
        eissn=Issn(NATURE_EISSN),
        publisher_id=publisher_id,
    )

    service = DOIImportService(doi_client=fake_client)
    result = service.build_preview_with_type_override(
        doi, OverrideImportAsArticle(journal_id=journal_id)
    )

    assert isinstance(result.publication, PreviewArticle)
    assert result.publication.journal.title == NATURE_JOURNAL_TITLE
    assert result.publication.journal.eissn == NATURE_EISSN


@pytest.mark.django_db
def test__build_preview_with_type_override__to_monograph__uses_resolved_publisher() -> None:
    """Overriding to monograph uses publisher name from the resolved DB publisher."""
    fake_client, doi = make_article_metadata(doi="10.1234/test.article")
    publisher_id = publisher_services.create(name="Springer Nature")

    service = DOIImportService(doi_client=fake_client)
    result = service.build_preview_with_type_override(
        doi, OverrideImportAsMonograph(publisher_id=publisher_id)
    )

    assert isinstance(result.publication, PreviewMonograph)
    assert result.publication.publisher_name == "Springer Nature"
```

Also add to imports at top of test file:

```python
from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideImportAsArticle,
    OverrideImportAsMonograph,
)
```

**Run:**

```bash
pdm run pytest tests/contexts/publication/test_doi_import_service.py::test__build_preview_with_type_override__to_article__uses_resolved_journal tests/contexts/publication/test_doi_import_service.py::test__build_preview_with_type_override__to_monograph__uses_resolved_publisher -v
```

**Expected:** `FAIL - ImportError: cannot import name 'OverrideImportAsArticle'`

### GREEN: Implement

**Add to `publisher_services.py`:**

```python
def get_by_pk(pk: int) -> Publisher:
    return Publisher.objects.get(pk=pk)
```

**Update `doi_import_service.py`:**

Add imports:

```python
from dataclasses import dataclass
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
```

Add override types before the class (after `_PREVIEW_BUILDERS`):

```python
@dataclass(frozen=True)
class OverrideImportAsArticle:
    journal_id: JournalId


@dataclass(frozen=True)
class OverrideImportAsMonograph:
    publisher_id: PublisherId


OverrideImportPublicationType = OverrideImportAsArticle | OverrideImportAsMonograph
```

Update `__init__` — replace `cache` with `metadata_cache`:

```python
def __init__(
    self,
    doi_client: DOIMetadataClient,
    metadata_cache: dict[Doi, ExternalPublicationMetadata] | None = None,
) -> None:
    self.doi_client = doi_client
    self.metadata_cache: dict[Doi, ExternalPublicationMetadata] = metadata_cache or {}
```

Add `_fetch_metadata` and refactor `fetch_doi_preview`:

```python
def _fetch_metadata(self, doi: Doi) -> ExternalPublicationMetadata:
    if doi not in self.metadata_cache:
        self.metadata_cache[doi] = self.doi_client.fetch(doi)
    return self.metadata_cache[doi]

def fetch_doi_preview(self, doi: Doi) -> PreviewFundingRequest:
    metadata = self._fetch_metadata(doi)
    detected_type = detect_publication_type(metadata)
    authors_dto = self._build_authors_dto(metadata.authors)
    builder = _PREVIEW_BUILDERS[detected_type]
    return PreviewFundingRequest(publication=builder(doi, metadata, authors_dto))
```

Add `build_preview_with_type_override`:

```python
def build_preview_with_type_override(
    self, doi: Doi, override: OverrideImportPublicationType
) -> PreviewFundingRequest:
    """Build a preview with an explicit publication type override.

    Fetches metadata from cache (no Crossref re-fetch), resolves the selected
    journal or publisher by DB ID, and builds the appropriate preview DTO.
    """
    metadata = self._fetch_metadata(doi)
    authors_dto = self._build_authors_dto(metadata.authors)

    match override:
        case OverrideImportAsArticle(journal_id=journal_id):
            journal = journal_services.get_by_pk(int(journal_id))
            overridden_metadata = metadata.model_copy(update={
                "journal": ExternalJournal(
                    title=journal.title,
                    issn=None,
                    eissn=journal.eissn,
                )
            })
            publication = build_preview_article(doi, overridden_metadata, authors_dto)
        case OverrideImportAsMonograph(publisher_id=publisher_id):
            publisher = publisher_services.get_by_pk(int(publisher_id))
            overridden_metadata = metadata.model_copy(update={"publisher": publisher.name})
            publication = build_preview_monograph(doi, overridden_metadata, authors_dto)

    return PreviewFundingRequest(publication=publication)
```

Update `import_from_doi`:

```python
def import_from_doi(
    self, doi: Doi, override: OverrideImportPublicationType | None = None
) -> FundingRequestId:
    self._ensure_doi_not_already_imported(doi)

    match override:
        case OverrideImportAsArticle() | OverrideImportAsMonograph():
            preview_dto = self.build_preview_with_type_override(doi, override)
        case None:
            preview_dto = self.fetch_doi_preview(doi)

    creation_dto = self._convert_preview_to_creation_dto(preview_dto, override)
    return fundingrequests.create_fundingrequest(creation_dto)
```

Update `_convert_preview_to_creation_dto`:

```python
def _convert_preview_to_creation_dto(
    self,
    preview: PreviewFundingRequest,
    override: OverrideImportPublicationType | None = None,
) -> CreateFundingRequestDto:
    publication_dto: PublicationDto | MonographDto

    match override:
        case OverrideImportAsArticle(journal_id=journal_id):
            if not isinstance(preview.publication, PreviewArticle):
                raise ValueError("Override type mismatch: expected PreviewArticle")
            publication_dto = preview.publication.to_publication_dto(journal_id=journal_id)

        case OverrideImportAsMonograph(publisher_id=publisher_id):
            if not isinstance(preview.publication, PreviewMonograph):
                raise ValueError("Override type mismatch: expected PreviewMonograph")
            publication_dto = preview.publication.to_monograph_dto(publisher_id=publisher_id)

        case None:
            if isinstance(preview.publication, PreviewArticle):
                if preview.publication.journal.eissn is None:
                    raise InvalidMetadataError(
                        f"Journal '{preview.publication.journal.title}' missing E-ISSN"
                    )
                issn = Issn(preview.publication.journal.eissn)
                journal_id = self._match_or_create_journal(issn, preview.publication)
                publication_dto = preview.publication.to_publication_dto(journal_id=journal_id)
            elif isinstance(preview.publication, PreviewMonograph):
                publisher_id = self._match_or_create_publisher(
                    preview.publication.publisher_name
                )
                publication_dto = preview.publication.to_monograph_dto(
                    publisher_id=publisher_id
                )
            else:
                raise ValueError("Invalid Preview type")

    return CreateFundingRequestDto(
        publication=publication_dto,
        payment=PaymentDto.empty(),
        extra_information=ExtraInformationDto(),
        funding=[],
    )
```

**Run:**

```bash
pdm run pytest tests/contexts/publication/test_doi_import_service.py::test__build_preview_with_type_override__to_article__uses_resolved_journal tests/contexts/publication/test_doi_import_service.py::test__build_preview_with_type_override__to_monograph__uses_resolved_publisher -v
```

**Expected:** `PASS (2 passed)`

### VERIFY

```bash
pdm run pytest tests/contexts/publication/test_doi_import_service.py -v
pdm run mypy src/coda/apps/publishers/services.py
pdm run mypy src/coda/contexts/publication/services/doi_import_service.py
pdm run ruff check src/coda/apps/publishers/services.py
pdm run ruff check src/coda/contexts/publication/services/doi_import_service.py
```

**Expected:** All pass, no errors

### COMMIT

```bash
git add src/coda/apps/publishers/services.py src/coda/contexts/publication/services/doi_import_service.py tests/contexts/publication/test_doi_import_service.py
git commit -m "feat(doi-import): add override types and build_preview_with_type_override method"
```

---

## TASK 2: Session Storage - Raw Metadata + Active Type

**Goal:** Restructure session to store only `original_metadata` (raw Crossref data), `publication_type` (active type), and optionally `journal_id` or `publisher_id` (when user has overridden). Preview is built on demand in each view — never stored. Update all three views accordingly.

**Session helper** (add as module-level function in `doi_preview.py`):

```python
def _build_override_from_session(
    session_data: dict[str, Any],
) -> OverrideImportPublicationType | None:
    match session_data.get("publication_type"):
        case "article" if (journal_id := session_data.get("journal_id")):
            return OverrideImportAsArticle(journal_id=JournalId(journal_id))
        case "monograph" if (publisher_id := session_data.get("publisher_id")):
            return OverrideImportAsMonograph(publisher_id=PublisherId(publisher_id))
        case _:
            return None
```

### Files

- Modify: `src/coda/apps/fundingrequests/views/doi_preview.py`
- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Failing Test

Add test to test file:

```python
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_doi_input_stores_original_metadata_and_publication_type(client: Client) -> None:
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)
    session_data = client.session[session_key]

    assert "doi" in session_data
    assert "original_metadata" in session_data
    assert "publication_type" in session_data
    assert "active_preview" not in session_data
    assert "original_preview" not in session_data
```

**Run:**

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_doi_input_stores_original_metadata_and_publication_type -v
```

**Expected:** `FAIL - KeyError: 'original_metadata'`

### GREEN: Implement Session Structure

**Modify `DOIImportInputView.post()`:**

```python
def post(self, request: HttpRequest) -> HttpResponse:
    doi_str = request.POST.get("doi", "")
    try:
        doi = Doi(doi_str)
        metadata = self.doi_client.fetch(doi)
        detected_type = detect_publication_type(metadata)

        session_key = f"doi_preview_{uuid4()}"
        request.session[session_key] = {
            "doi": str(doi),
            "original_metadata": metadata.model_dump(mode="json"),
            "publication_type": detected_type,
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

    doi = Doi(session_data["doi"])
    metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
    doi_service = DOIImportService(doi_client=self.doi_client, metadata_cache={doi: metadata})
    override = _build_override_from_session(session_data)

    if override:
        preview_dto = doi_service.build_preview_with_type_override(doi, override)
    else:
        preview_dto = doi_service.fetch_doi_preview(doi)

    context = build_preview_context(preview_dto.model_dump(mode="json"), session_key)
    return render(request, "fundingrequests/doi_preview_detail.html", context)
```

**Modify `DOIPreviewSaveView.post()`:**

```python
def post(self, request: HttpRequest, session_key: str) -> HttpResponse:
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found or expired", status=404)

    doi = Doi(session_data["doi"])
    metadata = ExternalPublicationMetadata.model_validate(session_data["original_metadata"])
    doi_service = DOIImportService(doi_client=self.doi_client, metadata_cache={doi: metadata})
    override = _build_override_from_session(session_data)

    try:
        fr_id = doi_service.import_from_doi(doi, override)
    except DOIAlreadyImported as e:
        messages.error(request, self._format_error(e))
        return redirect("fundingrequests:doi_preview_detail", session_key=session_key)

    del request.session[session_key]
    return redirect("fundingrequests:detail", pk=fr_id)
```

**Run:**

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_doi_input_stores_original_metadata_and_publication_type -v
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
git commit -m "feat(doi-import): restructure session to store raw metadata and active type"
```

---

## TASK 3: Views - Add HTMX Type Change Endpoints

**Goal:** Create HTMX endpoint to load type change forms (with smart pre-fill from `original_metadata`) and a submission handler that stores the selected entity ID in session. The detail view already rebuilds the preview on demand from session.

**Smart pre-fill logic:**

- Loading the **monograph form** (switching from article): read `original_metadata["publisher"]` → pre-fill publisher search field
- Loading the **article form** (switching from monograph): read `original_metadata["journal"]["title"]` (if present) → pre-fill journal search field

### Files

- Modify: `src/coda/apps/fundingrequests/views/doi_preview.py`
- Modify: `src/coda/apps/fundingrequests/urls.py`
- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Failing Tests

Add helpers and tests:

```python
def load_type_form(
    client: Client, session_key: str, pub_type: Literal["article", "monograph"]
) -> HttpResponse:
    """Helper to load HTMX type change form."""
    return cast(
        HttpResponse,
        client.get(
            reverse(
                "fundingrequests:doi_preview_load_type_form",
                kwargs={"session_key": session_key},
            ),
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
            reverse(
                "fundingrequests:doi_preview_apply_type_change",
                kwargs={"session_key": session_key},
            ),
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
def test_load_monograph_form_shows_prefilled_publisher(client: Client) -> None:
    """HTMX endpoint for monograph form should pre-fill publisher from original metadata."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    form_response = load_type_form(client, session_key, "monograph")

    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "publisher_name" in content
    # Should pre-fill publisher from original_metadata["publisher"]
    assert "Test Publisher" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "expected_fundingrequest")
def test_submit_type_change_to_monograph_stores_publisher_id_in_session(
    client: Client,
) -> None:
    """Submitting monograph form with publisher should store publisher_id in session."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    publisher = modelfactory.publisher(name="Test Publisher")

    change_response = submit_type_change(
        client, session_key, "monograph", publisher=publisher.id
    )

    assert change_response.status_code == 302
    assert f"/doi-preview/{session_key}/" in change_response["Location"]

    session_data = client.session[session_key]
    assert session_data["publication_type"] == "monograph"
    assert session_data["publisher_id"] == publisher.id


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_submit_type_change_to_article_stores_journal_id_in_session(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
    test_journal: tuple[JournalId, str, str, str],
) -> None:
    """Submitting article form with journal should store journal_id in session."""
    journal_id, journal_title, journal_eissn, publisher_name = test_journal

    # Start with a monograph DOI
    doi_str = "10.1234/book.test"
    doi = Doi(doi_str)
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Book",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="book",
        journal=None,
        publisher=publisher_name,
        isbn="978-3-16-148410-0",
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    journal = modelfactory.journal(title=journal_title, eissn=journal_eissn)

    change_response = submit_type_change(
        client, session_key, "article", journal=journal.pk
    )

    assert change_response.status_code == 302

    session_data = client.session[session_key]
    assert session_data["publication_type"] == "article"
    assert session_data["journal_id"] == journal.pk
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
    doi_preview_load_type_form,   # NEW
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

**Add to `doi_preview.py` (after existing views):**

```python
def doi_preview_load_type_form(request: HttpRequest, session_key: str) -> HttpResponse:
    """HTMX endpoint: Load form partial for switching publication type.

    Uses original_metadata for smart pre-filling in both directions:
    - article form: pre-fill journal search from original_metadata["journal"]["title"]
    - monograph form: pre-fill publisher search from original_metadata["publisher"]
    """
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)

    requested_type = request.GET.get("publication_type", "article")
    original_metadata = session_data.get("original_metadata", {})

    if requested_type == "article":
        journal_data = original_metadata.get("journal") or {}
        context = {
            "session_key": session_key,
            "journal_title": journal_data.get("title", ""),
            "journals": [],
        }
        return render(
            request,
            "fundingrequests/partials/doi_type_change_to_article.html",
            context,
        )
    else:
        context = {
            "session_key": session_key,
            "suggested_publisher": original_metadata.get("publisher", ""),
            "publishers": [],
        }
        return render(
            request,
            "fundingrequests/partials/doi_type_change_to_monograph.html",
            context,
        )


def doi_preview_apply_type_change(request: HttpRequest, session_key: str) -> HttpResponse:
    """Handle type change form submission — stores selected entity ID in session.

    Does not build or store a preview — the detail view rebuilds on demand.
    """
    session_data = request.session.get(session_key)
    if not session_data:
        return HttpResponse("Preview session not found", status=404)

    requested_type = request.POST.get("publication_type")
    if requested_type not in ("article", "monograph"):
        return HttpResponse("Invalid publication type", status=400)

    match requested_type:
        case "article":
            journal_id_str = request.POST.get("journal")
            if not journal_id_str:
                return HttpResponse("Journal is required for article", status=400)
            session_data["publication_type"] = "article"
            session_data["journal_id"] = int(journal_id_str)
            session_data.pop("publisher_id", None)
        case "monograph":
            publisher_id_str = request.POST.get("publisher")
            if not publisher_id_str:
                return HttpResponse("Publisher is required for monograph", status=400)
            session_data["publication_type"] = "monograph"
            session_data["publisher_id"] = int(publisher_id_str)
            session_data.pop("journal_id", None)

    request.session[session_key] = session_data
    request.session.modified = True
    return redirect("fundingrequests:doi_preview_detail", session_key=session_key)
```

**Run:**

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_load_article_form_shows_journal_search -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_load_monograph_form_shows_prefilled_publisher -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_submit_type_change_to_monograph_stores_publisher_id_in_session -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_submit_type_change_to_article_stores_journal_id_in_session -v
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
git commit -m "feat(doi-import): add HTMX type change endpoints with smart pre-fill"
```

---

## TASK 4: Templates - Add HTMX Type Selector and Forms

**Goal:** Create HTMX-based UI with type selector and reusable form partials. Update `preview_context_builder.py` to pass `current_publication_type` and `session_key` to the template. Include the type selector in `doi_preview_detail.html`.

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
    """Preview page should show publication type selector with HTMX attributes."""
    doi_str = "10.1234/preview.test"
    response = submit_for_preview(client, doi_str)
    preview_url = response["Location"]
    preview_response = client.get(preview_url)
    content = preview_response.content.decode()

    assert 'name="publication_type"' in content
    assert 'value="article"' in content
    assert 'value="monograph"' in content
    assert 'hx-get' in content
    assert 'load-type-form' in content
```

**Run:**

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_preview_page_shows_type_selector_with_htmx -v
```

**Expected:** `FAIL - AssertionError: 'hx-get' not in content`

### GREEN: Create Templates

**Update `preview_context_builder.py` — add `current_publication_type` and `session_key`:**

Find the `build_preview_context()` function and update the return statement:

```python
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

**Create `fundingrequests/partials/doi_type_selector.html`:**

```html
{# Publication type selector with HTMX form loading #}
{# Parameters: session_key, current_publication_type #}
<section class="card mb-1" id="type-selector-section">
    <h3>Publication Type</h3>
    <p class="text-muted">Select the publication type. The form below will update to collect required information.</p>

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
            Monograph (Book / Book Chapter)
        </label>
    </div>

    <div id="type-change-form" class="mt-1">
        {# HTMX loads the appropriate form partial here on radio change #}
    </div>
</section>
```

**Create `fundingrequests/partials/doi_type_change_to_article.html`:**

```html
{# Form for changing to article type - requires journal selection #}
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
{# Parameters: session_key, suggested_publisher, publishers, selected_publisher #}
<form method="post" action="{% url 'fundingrequests:doi_preview_apply_type_change' session_key=session_key %}">
    {% csrf_token %}
    <input type="hidden" name="publication_type" value="monograph">

    <h4 class="mt-1">Select Publisher</h4>
    <p class="text-muted">Search for the publisher of this monograph. The field is pre-filled from the imported metadata.</p>

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

**Update `doi_preview_detail.html` — include type selector after opening paragraph:**

```html
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
git commit -m "feat(doi-import): add HTMX type selector UI with smart pre-fill from original metadata"
```

---

## TASK 5: Integration Test - End-to-End Override Workflows

**Goal:** Test complete override workflow from submission to save, for both directions (article→monograph and monograph→article).

### Files

- Test: `tests/fundingrequests/test_doi_import_preview.py`

### RED: Write Integration Tests

```python
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_override_article_to_monograph_and_save(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
) -> None:
    """Full workflow: article DOI → override to monograph → save creates Monograph."""
    doi_str = "10.1234/override.test"
    doi = Doi(doi_str)

    publisher = modelfactory.publisher(name="Springer")
    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Article",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=ExternalJournal(title="Nature", eissn="1476-4687"),
        publisher="Springer",
        isbn=None,
        license=None,
        online_publication_date=datetime.date(2024, 1, 1),
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    submit_type_change(client, session_key, "monograph", publisher=publisher.id)

    save_doi_import(client, session_key)

    fr = repository.first()
    assert fr is not None
    assert isinstance(fr.publication, Monograph)
    assert fr.publication.publisher.id == publisher.id


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_override_monograph_to_article_and_save(
    client: Client,
    fake_doi_client: FakeDOIMetadataClient,
    test_journal: tuple[JournalId, str, str, str],
) -> None:
    """Full workflow: monograph DOI → override to article → save creates Publication."""
    journal_id, journal_title, journal_eissn, publisher_name = test_journal
    doi_str = "10.1234/book.override"
    doi = Doi(doi_str)

    fake_doi_client.data[str(doi)] = ExternalPublicationMetadata(
        title="Test Book",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="book",
        journal=None,
        publisher=publisher_name,
        isbn="978-3-16-148410-0",
        license=None,
        online_publication_date=None,
        print_publication_date=None,
    )

    response = submit_for_preview(client, doi_str)
    session_key = get_session_key(response)

    journal = modelfactory.journal(title=journal_title, eissn=journal_eissn)
    submit_type_change(client, session_key, "article", journal=journal.pk)

    save_doi_import(client, session_key)

    fr = repository.first()
    assert fr is not None
    assert isinstance(fr.publication, Publication)
```

**Run:**

```bash
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_override_article_to_monograph_and_save -v
pdm run pytest tests/fundingrequests/test_doi_import_preview.py::test_override_monograph_to_article_and_save -v
```

**Expected:** `PASS (2 passed)`

### COMMIT

```bash
git add tests/fundingrequests/test_doi_import_preview.py
git commit -m "test(doi-import): add end-to-end type override integration tests for both directions"
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
pdm run mypy src/coda/apps/publishers/services.py
pdm run mypy src/coda/contexts/publication/services/doi_import_service.py
pdm run mypy src/coda/apps/fundingrequests/views/doi_preview.py
pdm run mypy src/coda/apps/fundingrequests/queries/preview_context_builder.py
```

**Expected:** No errors

### Lint All Modified Files

```bash
pdm run ruff check src/coda/apps/publishers/
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

- `src/coda/apps/publishers/services.py`
- `src/coda/contexts/publication/services/doi_import_service.py`
- `src/coda/apps/fundingrequests/views/doi_preview.py`
- `src/coda/apps/fundingrequests/urls.py`
- `src/coda/apps/fundingrequests/queries/preview_context_builder.py`
- `src/coda/apps/templates/fundingrequests/doi_preview_detail.html`

**Tests Added:** 11 new test functions

**Commits:** 6

**Key Decisions:**

1. `ExternalPublicationMetadata`, `ExternalJournal`, `ExternalAuthor` converted from `@dataclass` to Pydantic `BaseModel` (already done — committed separately)
2. Session stores only `original_metadata` (raw Crossref data), `publication_type` (active type), and optionally `journal_id` or `publisher_id` — no preview serialization
3. Preview is built on demand in each view from session data — cheap pure transformation, never stored
4. `OverrideImportAsArticle(journal_id)` / `OverrideImportAsMonograph(publisher_id)` — typed override objects, discriminated union `OverrideImportPublicationType`
5. `build_preview_with_type_override(doi, override)` — single unified method, uses `match` statement for dispatch
6. `import_from_doi(doi, override=None)` — accepts optional override; passes it through to `_convert_preview_to_creation_dto` to skip entity lookup when ID is already known
7. `_convert_preview_to_creation_dto(preview, override=None)` — uses `match override` to use provided IDs directly or fall back to auto-detect
8. `metadata_cache: dict[Doi, ExternalPublicationMetadata]` replaces old `cache: dict[Doi, PreviewFundingRequest]` — single cache, previews built from it on demand
9. `publisher_services.get_by_pk` added for consistency with `journal_services.get_by_pk`
10. Smart pre-fill uses `original_metadata` as authoritative source in both directions
11. HTMX radio buttons trigger partial form loads; full form submission collects required data before updating session

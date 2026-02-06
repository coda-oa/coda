# DOI Import UI Design

## Overview

Add user interface for importing published articles via DOI into CODA's funding request system. Users enter a DOI, preview the fetched metadata, optionally edit via existing wizards, then save to database.

## Goals

1. **Fast path for published articles** - Users with DOI can create funding requests in seconds
2. **Reuse existing components** - Leverage update wizards and detail page template
3. **No premature persistence** - Journals/publishers/funding requests only created on final save
4. **Consistent UX** - Matches existing import workflow patterns

## Current State

- **Backend complete**: DOI import service exists (`doi_import_service.py`)
- **Entry point**: List page has "Import" button for JSON bulk import
- **Wizard system**: Session-based multi-step forms for creation/updates
- **Detail page**: Template displays funding request with edit buttons per section

## Approach

**Repository pattern with dependency injection** - Abstract storage layer so wizards and detail pages work with either database or session storage.

### Why Repository Pattern?

- **Separation of concerns**: Wizards don't know about storage mechanism
- **Testability**: Mock repositories for isolated testing
- **Extensibility**: Could add file-based drafts, Redis caching, etc.
- **Minimal changes**: Wizards just swap `get_object_or_404()` for `repository.get_by_id()`

### Why NOT simpler approaches?

- **Mode flags** (`if mode == "session"`): Violates Open/Closed, harder to test
- **Duplicate views**: 80% code duplication, maintenance nightmare
- **Pre-create in DB**: Leaves orphaned entities on cancel

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        User Flow                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. /fundingrequests/import/doi/                            │
│     └─> Enter DOI → Fetch metadata → Store in session       │
│                                                              │
│  2. /fundingrequests/import/doi/preview/                    │
│     └─> Show detail page (read-only, session data)          │
│         └─> "Edit Publication" → Update wizard (session)    │
│         └─> "Edit Funding" → Update wizard (session)        │
│         └─> "Save" → Persist to DB → Redirect to detail     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Repository Protocol Design

Three repository protocols abstract storage (database or session):

#### 1. FundingRequestRepository

```python
class FundingRequestRepository(Protocol):
    def get(self) -> FundingRequest:
        """Load funding request from storage"""
    
    def save(self, funding_request: FundingRequest) -> int:
        """Save funding request, return database ID"""
```

**Implementations:**
- `DatabaseFundingRequestRepository(funding_request_id: int)` - Load from DB by ID
- `SessionFundingRequestRepository(session: SessionStore)` - Load from session, create on save

#### 2. JournalRepository

```python
class JournalRepository(Protocol):
    def get_by_id(self, journal_id: int) -> Journal:
        """Get journal by ID (real or placeholder)"""
```

**Implementations:**
- `DatabaseJournalRepository()` - `Journal.objects.get(pk=id)`
- `SessionJournalRepository(session)` - Build from session attributes if `id <= 0`, else DB lookup

#### 3. PublisherRepository

```python
class PublisherRepository(Protocol):
    def get_by_id(self, publisher_id: int) -> Publisher:
        """Get publisher by ID (real or placeholder)"""
```

**Implementations:**
- `DatabasePublisherRepository()` - `Publisher.objects.get(pk=id)`
- `SessionPublisherRepository(session)` - Build from session attributes if `id <= 0`, else DB lookup

### Session Storage Format

**Key:** `doi_import_draft`

**Structure:**
```python
{
    "funding_request": {
        # FundingRequest serialized to dict
        "request_id": "...",
        "estimated_cost": {...},
        "external_funding": [...],
        ...
    },
    "journal_attributes": {
        # For journals not yet in database (journal_id = 0)
        "title": "Nature",
        "eissn": "1476-4687",
        "publisher_name": "Springer Nature"
    },
    "publisher_attributes": {
        # For publishers not yet in database (publisher_id = 0)
        "name": "Springer Nature"
    }
}
```

**Placeholder IDs:**
- `journal_id = 0` → Journal not in DB, use `journal_attributes`
- `publisher_id = 0` → Publisher not in DB, use `publisher_attributes`
- Real IDs (> 0) → Fetch from database

### Components to Create/Modify

#### New Components

1. **Repository protocols** (`src/coda/apps/fundingrequests/repositories/protocols.py`)
   - `FundingRequestRepository`
   - `JournalRepository`
   - `PublisherRepository`

2. **Database repository implementations** (`src/coda/apps/fundingrequests/repositories/database.py`)
   - `DatabaseFundingRequestRepository`
   - `DatabaseJournalRepository`
   - `DatabasePublisherRepository`

3. **Session repository implementations** (`src/coda/apps/fundingrequests/repositories/session.py`)
   - `SessionFundingRequestRepository`
   - `SessionJournalRepository`
   - `SessionPublisherRepository`

4. **DOI import views** (`src/coda/apps/fundingrequests/views/doi_import.py`)
   - `doi_import_form_view` - Enter DOI, fetch metadata
   - `doi_import_preview_view` - Show detail page with session data
   - `doi_import_save_view` - Persist to database

5. **DOI import form** (`src/coda/apps/fundingrequests/forms.py`)
   - `DOIImportForm` - Single DOI text field with validation

6. **Templates**
   - `fundingrequests/doi_import_form.html` - DOI input page
   - Update `fundingrequests/fundingrequest_import.html` - Add dropdown/tabs for DOI vs JSON

7. **URL patterns** (`src/coda/apps/fundingrequests/urls.py`)
   - `/import/doi/` - DOI input form
   - `/import/doi/preview/` - Temporary detail page
   - `/import/doi/save/` - Final save endpoint

#### Modified Components

1. **Update wizards** (`src/coda/apps/fundingrequests/views/wizard/update_article.py`)
   - Add `get_funding_request_repository()` method
   - Change `fundingrequest_repository.get_by_id()` → `self.get_funding_request_repository().get()`
   - Override method in DOI import versions to use session repository

2. **Wizard steps** (`src/coda/apps/fundingrequests/views/wizard/steps/`)
   - `JournalStep` - Add `get_journal_repository()`, use instead of `get_object_or_404()`
   - `PublisherStep` - Add `get_publisher_repository()`, use instead of `get_object_or_404()`

3. **Detail view query** (`src/coda/apps/fundingrequests/queries/detail.py`)
   - Add repository parameters to `get_detail_context()`
   - Change `Journal.objects.get()` → `journal_repository.get_by_id()`
   - Change `Publisher.objects.get()` → `publisher_repository.get_by_id()`

4. **Detail view** (`src/coda/apps/fundingrequests/views/detailview.py`)
   - Pass database repositories to `detail.get_detail_context()`

5. **Import list page** (update existing import button to dropdown)
   - Option 1: "Import from JSON"
   - Option 2: "Import from DOI"

## Data Flow

### Phase 1: DOI Input

```
User → /import/doi/
  ↓
Enters DOI: "10.1038/nature12373"
  ↓
POST to /import/doi/
  ↓
doi_import_service.import_from_doi(doi)
  ↓
FundingRequest created (in memory)
  ↓
Session storage:
  - funding_request dict
  - journal_attributes (if new)
  - publisher_attributes (if new)
  ↓
Redirect → /import/doi/preview/
```

### Phase 2: Preview & Edit

```
User → /import/doi/preview/
  ↓
detail.get_detail_context(
  fr_repository = SessionFundingRequestRepository(session),
  journal_repository = SessionJournalRepository(session),
  publisher_repository = SessionPublisherRepository(session)
)
  ↓
Render detail template (read-only)
  ↓
User clicks "Edit Publication"
  ↓
UpdatePublicationView with session repository
  ↓
Wizard steps use SessionJournalRepository
  ↓
Save back to session
  ↓
Redirect → /import/doi/preview/
```

### Phase 3: Final Save

```
User clicks "Save" on preview
  ↓
POST to /import/doi/save/
  ↓
SessionFundingRequestRepository.save(funding_request):
  1. Resolve journal_attributes → create/find journal → real ID
  2. Resolve publisher_attributes → create/find publisher → real ID
  3. Update funding_request with real IDs
  4. fundingrequests.create_fundingrequest(dto)
  5. Clean up session
  ↓
Redirect → /fundingrequests/<id>/ (real detail page)
```

## Error Handling

### DOI Fetch Errors

**Scenario:** DOI not found, API error, invalid metadata

**Handling:**
- Show detailed error inline on DOI input page
- Error messages:
  - `DOINotFoundError` → "DOI not found. Please verify the DOI is correct."
  - `InvalidMetadataError` → "Missing required metadata: {field}"
  - `DOIAlreadyImported` → "This DOI already exists. View: [link]"
  - Network errors → "Unable to fetch DOI metadata. Try again."
- User can correct DOI and retry
- No partial data saved to session

### Wizard Validation Errors

**Scenario:** User edits publication, enters invalid data

**Handling:**
- Standard Django form validation in wizard steps
- Errors displayed inline per field
- User cannot proceed until valid
- Changes saved to session only when valid

### Save Errors

**Scenario:** Database constraint violation, service error during final save

**Handling:**
- Wrap `save()` in try/except
- Roll back any created journals/publishers (use transaction)
- Show error message on preview page
- Keep session data intact so user can retry
- Log error for debugging

### Session Expiry

**Scenario:** User's session expires mid-workflow

**Handling:**
- Check for session data existence before rendering preview
- If missing: Redirect to `/import/doi/` with message "Session expired. Please start over."
- Session timeout: Use Django's default (2 weeks)

## Testing Strategy

### Unit Tests

**Repository implementations:**
- `DatabaseFundingRequestRepository.get()` loads correct funding request
- `SessionFundingRequestRepository.get()` deserializes from session
- `SessionJournalRepository.get_by_id(0)` builds from attributes
- `SessionJournalRepository.get_by_id(123)` fetches from DB
- `SessionFundingRequestRepository.save()` creates journals/publishers/funding request

**Views:**
- `doi_import_form_view` validates DOI format
- `doi_import_form_view` stores metadata in session on success
- `doi_import_preview_view` uses session repositories
- `doi_import_save_view` clears session after save

### Integration Tests

**Full DOI import flow:**
1. POST DOI → verify session storage
2. GET preview → verify detail renders from session
3. Edit publication → verify wizard updates session
4. POST save → verify funding request created in DB
5. Verify journal/publisher created if new
6. Verify session cleaned up

**Error scenarios:**
- Invalid DOI → error displayed, no session data
- Duplicate DOI → error with link to existing request
- Edit with invalid data → validation errors, session preserved
- Save failure → error displayed, session preserved

### Manual Testing Checklist

- [ ] Import existing article with existing journal
- [ ] Import article with new journal (auto-create)
- [ ] Import article with new publisher (auto-create)
- [ ] Edit publication metadata after import
- [ ] Edit funding info after import
- [ ] Cancel during preview (session cleaned up)
- [ ] Save creates correct funding request
- [ ] Invalid DOI shows clear error
- [ ] Duplicate DOI shows existing request link
- [ ] Session expiry handled gracefully

## Implementation Phases

### Phase 1: Repository Infrastructure (Foundation)

**Goal:** Create repository abstractions without breaking existing code

**Tasks:**
1. Create repository protocols (`protocols.py`)
2. Implement database repositories (wrappers around existing code)
3. Implement session repositories
4. Add unit tests for all repository implementations

**Deliverable:** Repository layer tested and ready for integration

**Estimated effort:** 1-2 days

---

### Phase 2: Refactor Wizards to Use Repositories

**Goal:** Update wizards to accept repositories via dependency injection

**Tasks:**
1. Add `get_funding_request_repository()` to update wizards
2. Add `get_journal_repository()` to `JournalStep`
3. Add `get_publisher_repository()` to `PublisherStep`
4. Update `detail.get_detail_context()` to accept repositories
5. Update `fundingrequest_detail` view to pass database repositories
6. Add integration tests verifying existing functionality unchanged

**Deliverable:** Existing wizards and detail page work identically (no regression)

**Estimated effort:** 1-2 days

---

### Phase 3: DOI Import UI (Core Feature)

**Goal:** Build DOI import user flow

**Tasks:**
1. Create `DOIImportForm`
2. Create `doi_import_form_view` (input DOI)
3. Create `doi_import_preview_view` (temporary detail page)
4. Create `doi_import_save_view` (persist to DB)
5. Create template `doi_import_form.html`
6. Add URL patterns
7. Update import button to dropdown (JSON vs DOI)
8. Wire up session repositories in DOI import views

**Deliverable:** Complete DOI import flow working end-to-end

**Estimated effort:** 2-3 days

---

### Phase 4: DOI Import Edit Integration

**Goal:** Allow editing imported data via wizards

**Tasks:**
1. Create `DOIImportUpdatePublicationView` (inherits from `UpdatePublicationView`)
2. Override `get_funding_request_repository()` to use session
3. Override `get_journal_repository()` to use session
4. Same for `DOIImportUpdateFundingView`
5. Same for `DOIImportUpdateExtraInformationView`
6. Update preview template to link to DOI import update views
7. Add integration tests for edit workflow

**Deliverable:** Users can edit all sections before final save

**Estimated effort:** 1-2 days

---

### Phase 5: Error Handling & Polish

**Goal:** Production-ready error handling and UX

**Tasks:**
1. Add error handling for all DOI fetch errors
2. Add transaction rollback for save failures
3. Add session expiry handling
4. Improve error messages (user-friendly)
5. Add loading states (HTMX/CSS spinners)
6. Add success messages after save
7. Comprehensive error scenario testing

**Deliverable:** Robust error handling, polished UX

**Estimated effort:** 1-2 days

---

### Phase 6: Documentation & Cleanup

**Goal:** Production-ready feature

**Tasks:**
1. Add docstrings to all new modules
2. Update user documentation (if exists)
3. Code review and refactoring
4. Performance testing (ensure no N+1 queries)
5. Accessibility review (keyboard navigation, screen readers)

**Deliverable:** Feature ready for production deployment

**Estimated effort:** 1 day

---

## Total Estimated Effort: 7-12 days

## Implementation Notes

### Dependency Injection Strategy

**Default behavior (existing code):**
```python
class UpdatePublicationView(Wizard):
    def get_funding_request_repository(self) -> FundingRequestRepository:
        # Default: database repository
        return DatabaseFundingRequestRepository(self.kwargs["pk"])
    
    def prepare(self, request):
        repo = self.get_funding_request_repository()
        fr = repo.get()  # Works with both DB and session!
```

**DOI import override:**
```python
class DOIImportUpdatePublicationView(UpdatePublicationView):
    def get_funding_request_repository(self) -> FundingRequestRepository:
        # Override: session repository
        return SessionFundingRequestRepository(self.request.session)
```

**Benefits:**
- Existing views unchanged (no regression)
- Override pattern familiar to Django developers
- Easy to test (pass mock repository)

### FundingRequest Serialization

Need `FundingRequest.to_dict()` and `FundingRequest.from_dict()` for session storage:

```python
class FundingRequest:
    def to_dict(self) -> dict:
        return {
            "request_id": str(self.request_id),
            "publication": self.publication.to_dict(),
            "estimated_cost": self.estimated_cost.to_dict(),
            "external_funding": [ef.to_dict() for ef in self.external_funding],
            # ...
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FundingRequest":
        return cls(
            request_id=PublicFundingRequestId(data["request_id"]),
            publication=Publication.from_dict(data["publication"]),
            # ...
        )
```

**Consideration:** Existing domain objects may not have these methods. Two options:
1. Add serialization methods to domain models (couples domain to session storage)
2. Create separate serializer/deserializer functions (keeps domain clean)

**Recommendation:** Use separate serializers to keep domain models pure.

### URL Structure

```
/fundingrequests/import/          # JSON bulk import (existing)
/fundingrequests/import/doi/      # DOI import form (new)
/fundingrequests/import/doi/preview/  # Temporary detail page (new)
/fundingrequests/import/doi/save/     # Final save endpoint (new)

# DOI import update wizards (new)
/fundingrequests/import/doi/edit/publication/
/fundingrequests/import/doi/edit/funding/
/fundingrequests/import/doi/edit/extra/
```

### Template Reuse

**Detail page template reuse:**

The temporary detail page uses the same template as the real detail page, but:
- Hide review section (no review yet)
- Hide labels section (no labels yet)
- Replace "Edit" buttons with DOI import versions
- Add "Save" and "Cancel" buttons at top

**Implementation:**
```django
{# fundingrequests/doi_import_preview.html #}
{% extends "fundingrequests/fundingrequest_detail.html" %}

{% block extra_buttons %}
    <a href="{% url 'fundingrequests:doi_import_save' %}" 
       role="button" 
       class="primary">Save Funding Request</a>
    <a href="{% url 'fundingrequests:list' %}" 
       role="button" 
       class="secondary">Cancel</a>
{% endblock %}

{% block review_section %}
    {# Hide review section #}
{% endblock %}

{% block labels_section %}
    {# Hide labels section #}
{% endblock %}
```

## Open Questions

1. **Session cleanup:** Should we auto-cleanup abandoned DOI imports after X days?
2. **Multiple drafts:** Should users be able to have multiple DOI imports in progress?
3. **Back button:** What happens if user hits back button during wizard?
4. **Concurrent edits:** What if user opens same DOI import in two tabs?

**Proposed answers:**
1. Use Django's session cleanup (automatic)
2. No - single draft per user (simpler, covers 99% use case)
3. Session state preserved, wizard continues normally
4. Last save wins (acceptable for single-user workflow)

## Success Criteria

- [ ] User can import article via DOI in < 30 seconds
- [ ] All imported data editable before save
- [ ] No orphaned journals/publishers in database
- [ ] Clear error messages for all failure scenarios
- [ ] All existing tests pass (no regression)
- [ ] 90%+ test coverage for new code
- [ ] Performance: < 2 seconds for DOI fetch
- [ ] Performance: < 1 second for preview render
- [ ] Accessibility: WCAG 2.1 AA compliant

## Future Enhancements (Out of Scope)

- Batch DOI import (CSV upload)
- DOI auto-detection from URLs
- Pre-fill from CrossRef data
- Save as draft (named drafts)
- DOI import history
- Duplicate detection suggestions

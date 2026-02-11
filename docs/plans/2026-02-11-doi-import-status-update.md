# DOI Import - Status Update (February 11, 2026)

## Current Implementation Status

### ✅ Phase 1: Core Preview Workflow (COMPLETE)

**Implemented Components:**

1. **DOI Input Form** (`DOIImportInputView`)
   - ✅ GET: Display DOI input form
   - ✅ POST: Fetch metadata, create session, redirect to preview
   - ✅ Error handling for DOIFetchError and DOINotFoundError
   - ✅ User-friendly error messages in template

2. **Preview Detail Page** (`DOIPreviewDetailView`)
   - ✅ Load preview data from session (not database)
   - ✅ Display publication metadata, authors, costs, funding
   - ✅ Reuses template partials from detail view (DRY)
   - ✅ Edit buttons present (placeholders - not yet functional)
   - ✅ Sticky save/cancel bar at bottom (width-aligned with content)

3. **Save to Database** (`DOIPreviewSaveView`)
   - ✅ Reconstruct DTOs from session data
   - ✅ Persist to database via `fundingrequests.create_fundingrequest()`
   - ✅ Clean up session after save
   - ✅ Redirect to funding request detail page

4. **Template DRY Refactoring**
   - ✅ Created reusable partials (request_details, publication, costs_funding, additional_info)
   - ✅ Both detail view and preview view use same partials
   - ✅ Eliminated ~170 lines of template duplication

5. **Preview Context Builder**
   - ✅ Converts session DTOs → Detail models for templates
   - ✅ Efficient bulk DB lookups for institutions and funding organizations
   - ✅ Supports preview mode (no request_details, different edit URLs)

6. **Session Storage Pattern**
   - ✅ Stores DTO fields individually (publication, payment, funding, extra_information)
   - ✅ Uses `to_post_data()` for serialization (handles None → "" conversion)
   - ✅ Multiple previews can coexist in same session
   - ✅ Session cleaned up after save

**Files Created:**

- `src/coda/apps/fundingrequests/views/doi_preview.py` (3 views)
- `src/coda/apps/fundingrequests/queries/preview_context_builder.py`
- `src/coda/apps/templates/fundingrequests/doi_import_input.html`
- `src/coda/apps/templates/fundingrequests/doi_preview_detail.html`
- `src/coda/apps/templates/fundingrequests/partials/*.html` (4 partials)
- `tests/fundingrequests/test_doi_import_preview.py` (11 tests)

**Files Modified:**

- `src/coda/apps/fundingrequests/urls.py` - Added DOI import URL patterns
- `src/coda/apps/fundingrequests/queries/detail.py` - Added edit URLs to context
- `src/coda/apps/templates/fundingrequests/fundingrequest_detail.html` - Refactored to use partials
- `src/coda/contexts/fundingrequest/dto/commands.py` - Fixed PaymentDto serialization

**Test Coverage:**

```
✅ 11/11 DOI import preview tests passing
✅ 16/16 wizard tests passing (no regressions)
✅ 176/176 total fundingrequests tests passing
```

**Test Scenarios Covered:**

1. DOI input → preview redirect
2. Preview page displays metadata
3. Preview doesn't persist until saved
4. Save creates correct FundingRequest
5. Save redirects to detail page
6. Multiple previews can coexist
7. Session cleanup after save
8. DOI input form displays correctly (GET)
9. Error handling for fetch failures
10. Error handling for non-existent DOIs

---

## ❌ Phase 2: Edit Workflows (NOT STARTED)

**Status:** BLOCKED - Requires Strategy Pattern implementation

**Current State:**

- Edit button URLs are placeholders: `#edit-publication-{session_key}`
- No DOI import-specific wizards exist
- Existing update wizards hardcoded to database persistence

**Required Work:**

### Strategy Pattern Infrastructure

See `/app/docs/plans/2026-02-09-doi-import-revised-approach.md` for full design.

**Key Components to Implement:**

1. **`FundingRequestPersistenceStrategy` Protocol**

   ```python
   class FundingRequestPersistenceStrategy(Protocol):
       def load_publication_data(self) -> dict[str, Any]: ...
       def save_publication_data(self, store: Store) -> None: ...
       def load_funding_data(self) -> dict[str, Any]: ...
       def save_funding_data(self, store: Store) -> None: ...
       def load_extra_information_data(self) -> dict[str, Any]: ...
       def save_extra_information_data(self, store: Store) -> None: ...
   ```

2. **`DatabasePersistenceStrategy`** (existing behavior)
   - Load from database via repository
   - Save via service methods

3. **`SessionPersistenceStrategy`** (DOI import)
   - Load from session DTO
   - Save back to session DTO

4. **Refactor Update Wizards**
   - Add `get_persistence_strategy()` method
   - Update `prepare()` to use strategy
   - Update `complete()` to use strategy

5. **DOI Import Update Wizards**
   - `DOIImportUpdatePublicationView` - inherits from `UpdateArticlePublicationView`
   - `DOIImportUpdateFundingView` - inherits from `UpdateFundingView`
   - `DOIImportUpdateSubmitterView` - inherits from `UpdateExtraInformationView`
   - Override `get_persistence_strategy()` to return `SessionPersistenceStrategy`

**Estimated Complexity:** HIGH - Requires refactoring existing wizards

---

## 🚨 Critical Discovery: Publication Type Detection

### The Problem

**Current Implementation:**

- `DOIImportService.prepare_funding_request_dto()` always builds `PublicationDto` (article)
- Always calls `_match_or_create_journal()`
- Fails if journal metadata missing (which it would be for monographs)

**Crossref provides publication type:**

```python
ExternalPublicationMetadata.publication_type: str  # e.g., "journal-article", "book", "monograph"
```

**CODA has two DTO types:**

- `PublicationDto` - articles (has `journal: JournalDto`)
- `MonographDto` - monographs (has `publisher: PublisherId`)

### The Challenge

**Automatic detection is error-prone:**

- Book chapters might be classified differently
- Proceedings articles (article or monograph?)
- Theses/dissertations
- Preprints
- Conference papers

**Example Ambiguities:**

| Crossref Type | CODA Type | Confidence |
|---------------|-----------|------------|
| `journal-article` | Article | ✅ High |
| `book` | Monograph | ✅ High |
| `book-chapter` | Monograph | ⚠️ Medium (could be journal article) |
| `proceedings-article` | Article? | ⚠️ Low |
| `dissertation` | Monograph? | ⚠️ Low |
| `report` | Unknown | ❌ Very Low |

### Proposed Solution: User Confirmation Step

**New Workflow:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: DOI Input                                               │
│ [DOI input form]                                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Publication Type Confirmation (NEW)                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Title: "Example Publication"                                │ │
│ │ Publisher: Springer                                         │ │
│ │ Journal: Nature (if present)                                │ │
│ │ Detected Type (from Crossref): "book-chapter"               │ │
│ │                                                             │ │
│ │ This publication is a:                                      │ │
│ │ ● Article (in a journal)  ← Auto-detected                   │ │
│ │ ○ Monograph (book)                                          │ │
│ │                                                             │ │
│ │ [Cancel] [Continue to Preview]                              │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Preview (with appropriate fields)                       │
│ - Article preview shows journal                                 │
│ - Monograph preview shows publisher                             │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits:**

- ✅ User has final say - auto-detection can be overridden
- ✅ Transparent - shows Crossref type and our interpretation
- ✅ Educational - explains why we're asking
- ✅ Handles edge cases - user can correct classification
- ✅ Testable - each step isolated

**Required Implementation:**

1. **New View: `DOIPublicationTypeConfirmationView`**
   - GET: Display metadata + type selection form
   - POST: Build appropriate DTO based on user selection

2. **Update `DOIImportInputView`**
   - Store raw metadata in session (don't build DTO yet)
   - Redirect to type confirmation instead of preview

3. **New Service Methods:**

   ```python
   class DOIImportService:
       def fetch_metadata(self, doi: Doi) -> ExternalPublicationMetadata:
           """Fetch metadata without building DTO."""
           
       def detect_publication_type(self, metadata: ExternalPublicationMetadata) -> str:
           """Detect publication type (best guess). Returns "article" or "monograph"."""
           
       def build_dto_from_metadata(
           self, 
           metadata: ExternalPublicationMetadata,
           publication_type: Literal["article", "monograph"]
       ) -> PublicationDto | MonographDto:
           """Build DTO from metadata with explicit publication type."""
   ```

4. **New Template: `doi_type_confirmation.html`**
   - Radio buttons for article/monograph
   - Shows title, publisher, journal (if present)
   - Shows Crossref raw type
   - Explains why we're asking (collapsible details)

5. **Update Preview Components:**
   - Preview template: Show "Article" or "Monograph" icon dynamically
   - Preview context builder: Detect DTO type (has journal vs publisher)
   - Preview detail: Show journal for articles, publisher for monographs

**Estimated Complexity:** MEDIUM - New workflow step, branching logic

---

## 📋 Updated Implementation Roadmap

### Immediate Next Steps (High Priority)

**Option A: Publication Type Detection (Recommended)**

- Blocking issue - cannot import monographs currently
- Medium complexity
- High user value
- Estimated: 1-2 sessions

**Option B: Edit Workflows (Strategy Pattern)**

- Blocking feature completion
- High complexity
- Required for production use
- Estimated: 3-4 sessions

**Option C: Navigation Integration (Quick Win)**

- Add "Import from DOI" button to funding request list
- Low complexity
- Makes feature discoverable
- Estimated: < 1 session

### Medium Priority

1. **Better Error Messages**
   - Specific handling for DOINotFoundError vs DOIFetchError
   - User-friendly explanations
   - Retry suggestions

2. **Session Management**
   - Session expiration warnings
   - "Resume draft" functionality
   - Clean up orphaned sessions

3. **Validation Before Save**
   - Full DTO validation before final save
   - Display validation errors in preview
   - Prevent invalid data from being saved

### Low Priority (Polish)

1. **Duplicate Detection**
   - Check if DOI already exists before import
   - Offer to navigate to existing funding request
   - Warning if duplicate detected

2. **Loading States**
   - Spinner during DOI fetch
   - Progress indicators for multi-step workflow

3. **Additional Publication Types**
   - Support for proceedings
   - Support for theses/dissertations
   - Support for preprints

---

## 🔍 Technical Debt & Observations

### Session Storage Architecture

**Current Pattern (Works Well):**

```python
# Store individual DTO fields
session[f"doi_preview_{uuid4()}"] = {
    "publication": dto.publication.to_post_data(),
    "payment": dto.payment.to_post_data(),
    "funding": [f.to_post_data() for f in dto.funding],
    "extra_information": dto.extra_information.to_post_data(),
}
```

**Why individual fields?**

- `CreateFundingRequestDto.publication` is polymorphic (`PublicationBaseDto` - abstract)
- Pydantic can't deserialize abstract base types without discriminators
- Storing fields individually allows manual reconstruction with correct concrete type

**Future Improvement:**

- Add discriminator field to DTOs for automatic polymorphic deserialization
- Would allow storing entire `CreateFundingRequestDto` as single blob

### Template Partials Success

**Before Refactoring:**

- `fundingrequest_detail.html`: ~300 lines
- `doi_preview_detail.html`: Would have been ~250 lines (duplication)

**After Refactoring:**

- `fundingrequest_detail.html`: ~130 lines (uses partials)
- `doi_preview_detail.html`: ~33 lines (uses partials)
- `partials/*.html`: 4 files, ~50 lines each

**Savings:** ~270 lines of eliminated duplication

**Benefits:**

- Single source of truth for display logic
- Bug fixes apply to both views automatically
- Easier to maintain and extend

### DTO Serialization Pattern

**Key Discovery:**

```python
# DTOs use OptionalFromStr for optional fields
class PaymentDto(CodaBaseDto):
    external_costsplitting: OptionalFromStr[bool]

# to_post_data() converts None → ""
dto.to_post_data()  # {"external_costsplitting": ""}

# model_validate() converts "" → None
PaymentDto.model_validate(data)  # external_costsplitting = None
```

**Fixed in this session:**

- `PaymentDto.external_costsplitting` was `bool | None` (wrong)
- Changed to `OptionalFromStr[bool]` (correct)
- Now serializes/deserializes correctly through session

---

## 🧪 Testing Strategy

### Current Test Coverage

**Preview Workflow (11 tests):**

1. ✅ DOI input redirects to preview
2. ✅ Preview displays metadata
3. ✅ Preview doesn't persist until saved
4. ✅ Save creates correct FundingRequest
5. ✅ Save redirects to detail page
6. ✅ Preview stays session-only
7. ✅ Multiple previews coexist
8. ✅ Session cleanup after save
9. ✅ Input form displays (GET)
10. ✅ Fetch error handling
11. ✅ Not found error handling

**Missing Test Coverage:**

**Publication Type Detection:**

- [ ] Auto-detect article from "journal-article"
- [ ] Auto-detect monograph from "book"
- [ ] Auto-detect monograph from "book-chapter"
- [ ] User override article → monograph
- [ ] User override monograph → article
- [ ] Monograph DTO built correctly
- [ ] Monograph preview displays correctly
- [ ] Monograph save creates Monograph in DB

**Edit Workflows:**

- [ ] Edit publication from preview
- [ ] Edit funding from preview
- [ ] Edit submitter from preview
- [ ] Session updated after edit
- [ ] Return to preview after edit
- [ ] Multiple edits accumulate correctly

**Error Scenarios:**

- [ ] Invalid DOI format
- [ ] Duplicate DOI detection
- [ ] Session expiration during workflow
- [ ] Journal creation failure
- [ ] Publisher creation failure

---

## 📊 Metrics & Progress

### Lines of Code

**Production Code:**

- `doi_preview.py`: 163 lines
- `preview_context_builder.py`: ~150 lines (estimated)
- Templates (new): ~300 lines total
- Templates (refactored): -170 lines (eliminated duplication)

**Test Code:**

- `test_doi_import_preview.py`: 476 lines (11 tests)

**Total:** ~750 lines new code, -170 lines removed duplication

### Feature Completion

```
Phase 1: Core Preview Workflow      [████████████████████████] 100%
Phase 2: Edit Workflows              [░░░░░░░░░░░░░░░░░░░░░░░░]   0%
Phase 3: Publication Type Detection  [░░░░░░░░░░░░░░░░░░░░░░░░]   0%
Phase 4: Navigation Integration      [░░░░░░░░░░░░░░░░░░░░░░░░]   0%
Phase 5: Polish & Error Handling     [███░░░░░░░░░░░░░░░░░░░░░]  15%

Overall Feature Completion:          [█████░░░░░░░░░░░░░░░░░░░]  23%
```

### User-Facing Functionality

**Working Today:**

- ✅ Enter DOI
- ✅ See preview of imported metadata
- ✅ Save to database
- ✅ View in detail page

**Not Working Yet:**

- ❌ Edit imported data before saving
- ❌ Import monographs
- ❌ Choose publication type
- ❌ Navigate to feature from main UI

**Blockers for Production:**

1. Edit workflows (critical - users need to correct data)
2. Publication type detection (critical - monographs fail)
3. Navigation integration (high - feature not discoverable)

---

## 🎯 Recommended Next Session

### Priority 1: Publication Type Detection

**Why:**

- Blocks monograph imports (currently fail)
- Medium complexity (manageable)
- High user value

**Deliverables:**

1. `DOIPublicationTypeConfirmationView` (GET + POST)
2. Update `DOIImportInputView` to redirect to confirmation
3. `detect_publication_type()` service method
4. `build_dto_from_metadata()` service method (with type parameter)
5. `doi_type_confirmation.html` template
6. Update preview template to show article/monograph dynamically
7. Tests for detection logic and user override

**Estimated Time:** 1-2 sessions

### Alternative: Navigation Integration (Quick Win)

**Why:**

- Makes feature discoverable
- Low complexity
- Can be done in < 1 session

**Deliverables:**

1. Add "Import from DOI" button to funding request list page
2. Add breadcrumbs to preview page
3. Update navigation tests

**Estimated Time:** < 1 session

---

## 📝 Known Issues & Limitations

### Current Limitations

1. **Article-only support**
   - Monograph imports fail or create invalid data
   - No publication type selection

2. **No edit capability**
   - Users cannot correct imported metadata
   - Must accept as-is or cancel entirely

3. **Not discoverable**
   - No link from main UI
   - Users don't know feature exists

4. **Limited error messages**
   - Generic error handling
   - No specific guidance for common failures

5. **No duplicate detection**
   - Can import same DOI multiple times
   - Creates duplicate funding requests

### Technical Limitations

1. **Session-based only**
   - No "save draft" functionality
   - Session expiration loses work

2. **Manual DTO reconstruction**
   - Due to polymorphic publication field
   - Could be improved with discriminators

3. **No validation before save**
   - Invalid data can reach database
   - Errors occur at persistence time

---

## 🔗 Related Documents

- **Original Plan:** `/app/docs/plans/2026-02-09-doi-import-revised-approach.md`
- **UI Design:** `/app/docs/plans/2026-02-06-doi-import-ui-design.md`
- **Strategy Pattern:** See "Solution: Strategy Pattern" section in revised approach doc

---

## 📅 Change History

| Date | Changes | Author |
|------|---------|--------|
| 2026-02-11 | Initial status document created | OpenAgent |
| 2026-02-11 | Added publication type detection analysis | OpenAgent |
| 2026-02-11 | Updated implementation roadmap | OpenAgent |

---

## ✅ Summary for Next Developer

**What's Working:**

- DOI input → preview → save workflow complete
- Session-based preview (doesn't persist until save)
- Template reuse (DRY partials)
- Comprehensive test coverage (11 tests)
- Error handling for fetch failures

**What's Blocking Production:**

1. **Cannot edit imported data** (need Strategy Pattern)
2. **Cannot import monographs** (need type detection)
3. **Feature not discoverable** (need navigation)

**Best Next Step:**
Implement publication type detection with user confirmation. This unblocks monograph imports and provides better user experience with edge cases.

**Files to Focus On:**

- `src/coda/contexts/publication/services/doi_import_service.py` - Add type detection
- `src/coda/apps/fundingrequests/views/doi_preview.py` - Add confirmation view
- `tests/fundingrequests/test_doi_import_preview.py` - Add type detection tests

---

## 🤔 Outstanding Questions for Domain Experts

These questions arose during design of the publication type detection feature:

1. **Book chapters vs articles:**
   - How should `book-chapter` be classified by default? (Currently: monograph)
   - Can articles appear in books? (Probably rare, but should we allow override?)
   - Should `book-section` be treated differently from `book-chapter`?

2. **Proceedings:**
   - Should `proceedings-article` default to article or monograph?
   - Are conference proceedings more like journals or books in CODA's model?
   - Need domain expert input on classification

3. **Default behavior for unknown types:**
   - If Crossref returns an unknown `publication_type`, should we:
     - Default to article (safest guess)?
     - Fail with error (safer, but less user-friendly)?
     - **Current proposal:** Show warning, require user to choose
   
4. **Testing with real DOIs:**
   - Do we have example monograph DOIs to test against?
   - Should we add real-world test cases for edge cases (proceedings, theses, etc.)?
   - Would be valuable to test against actual Crossref data

5. **Thesis/Dissertation classification:**
   - Should these be monographs or a separate category?
   - Current proposal: Treat as monograph (book-like)

These questions don't block implementation (user confirmation handles all cases), but answering them would improve default detection accuracy.

# DOI Import - Revised Approach (DTO + Strategy Pattern)

## Problem Statement

The original plan assumed we needed a repository pattern to abstract database vs session storage. However, after examining the wizard code, we discovered:

1. **Wizards already use DTOs for session storage** - `prepare()` converts domain → DTO → `to_post_data()` → session
2. **The service now persists directly** - `DOIImportService.import_from_doi()` returns `FundingRequestId`
3. **We need abstraction around wizard persistence strategy**, not data access

## The Real Challenge

Update wizards like `UpdatePublicationView` have two hardcoded assumptions:

**`prepare()` - Load from database:**
```python
def prepare(self, request: HttpRequest) -> None:
    fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])  # Database
    dto = PublicationDto.from_publication(fr.publication)
    store["publication_step"] = dto.to_post_data(...)
```

**`complete()` - Save to database:**
```python
def complete(self, **kwargs: Any) -> None:
    metadata = UpdatePublicationMetadataCommand(**store["publication_step"])
    fundingrequests.update_publication_metadata(pk, metadata)  # Database update
```

For DOI import preview workflow:
- **`prepare()`**: Should load from session DTO, not database
- **`complete()`**: Should update session DTO, not call service methods

## Solution: Strategy Pattern

### Core Abstraction: `FundingRequestPersistenceStrategy`

```python
from typing import Protocol
from coda.apps.wizard import Store

class FundingRequestPersistenceStrategy(Protocol):
    """Define how wizards load and persist funding request data.
    
    Different strategies handle different persistence mechanisms:
    - DatabasePersistenceStrategy: Load from DB, save via service methods
    - SessionPersistenceStrategy: Load from session DTO, save to session DTO
    """
    
    def load_publication_data(self) -> dict[str, Any]:
        """Load publication data for wizard initialization.
        
        Returns dict ready for session store (from to_post_data()).
        """
        ...
    
    def save_publication_data(self, store: Store) -> None:
        """Persist publication changes from wizard."""
        ...
    
    def load_funding_data(self) -> dict[str, Any]:
        """Load cost and funding data for wizard initialization."""
        ...
    
    def save_funding_data(self, store: Store) -> None:
        """Persist funding changes from wizard."""
        ...
    
    def load_extra_information_data(self) -> dict[str, Any]:
        """Load extra information for wizard initialization."""
        ...
    
    def save_extra_information_data(self, store: Store) -> None:
        """Persist extra information changes from wizard."""
        ...
```

### Implementation 1: Database Strategy (Existing Behavior)

```python
class DatabasePersistenceStrategy:
    """Load from database, persist via service methods (existing behavior)."""
    
    def __init__(self, funding_request_id: int):
        self.funding_request_id = funding_request_id
    
    def load_publication_data(self) -> dict[str, Any]:
        from coda.apps.fundingrequests import repository
        
        fr = repository.get_article_request(self.funding_request_id)
        dto = PublicationDto.from_publication(fr.publication)
        return {
            "publication_step": dto.to_post_data(exclude={"journal", "contracts"}),
            "journal": fr.publication.journal,
            "contracts": [c.to_post_data() for c in dto.contracts],
        }
    
    def save_publication_data(self, store: Store) -> None:
        from coda.contexts.fundingrequest.services import fundingrequests
        
        metadata = UpdatePublicationMetadataCommand(**store["publication_step"])
        fundingrequests.update_publication_metadata(
            self.funding_request_id, 
            metadata
        )
        
        # Update journal + contracts if present
        if "journal" in store:
            journal = JournalId(store["journal"])
            contract_dtos = [ContractYearDto(**c) for c in store["contracts"]]
            fundingrequests.update_publication_journal_and_contracts(
                self.funding_request_id,
                journal,
                contract_dtos
            )
    
    def load_funding_data(self) -> dict[str, Any]:
        from coda.apps.fundingrequests import repository
        
        fr = repository.get_by_id(self.funding_request_id)
        payment_dto = PaymentDto.from_payment(fr.estimated_cost)
        return {
            "cost": payment_dto.to_post_data(),
            "funding": [
                ExternalFundingDto.from_external_funding(ef).to_post_data()
                for ef in fr.external_funding
            ],
        }
    
    def save_funding_data(self, store: Store) -> None:
        from coda.contexts.fundingrequest.services import fundingrequests
        
        cost = PaymentDto(**store["cost"])
        funding = [ExternalFundingDto(**f) for f in store.get("funding", [])]
        fundingrequests.update_funding(self.funding_request_id, cost, funding)
    
    # ... similar for extra_information
```

### Implementation 2: Session Strategy (DOI Import)

```python
class SessionPersistenceStrategy:
    """Load from session DTO, persist back to session DTO (DOI import preview)."""
    
    def __init__(self, session: SessionStore, draft_key: str = "doi_import_draft"):
        self.session = session
        self.draft_key = draft_key
    
    def load_publication_data(self) -> dict[str, Any]:
        """Load from session DTO (already in to_post_data() format)."""
        draft = self.session[self.draft_key]
        return {
            "publication_step": draft["publication_step"],
            "journal": draft["journal"],
            "contracts": draft["contracts"],
        }
    
    def save_publication_data(self, store: Store) -> None:
        """Update session DTO with wizard changes."""
        draft = self.session[self.draft_key]
        draft["publication_step"] = store["publication_step"]
        draft["journal"] = store["journal"]
        draft["contracts"] = store["contracts"]
        self.session[self.draft_key] = draft
        self.session.save()
    
    def load_funding_data(self) -> dict[str, Any]:
        draft = self.session[self.draft_key]
        return {
            "cost": draft["cost"],
            "funding": draft.get("funding", []),
        }
    
    def save_funding_data(self, store: Store) -> None:
        draft = self.session[self.draft_key]
        draft["cost"] = store["cost"]
        draft["funding"] = store.get("funding", [])
        self.session[self.draft_key] = draft
        self.session.save()
    
    # ... similar for extra_information
```

### Refactored Wizard (Database Strategy)

```python
class UpdatePublicationView(LoginRequiredMixin, Wizard):
    store_name = "update_publication_wizard"
    store_factory = SessionStore
    steps = [PublicationStep.for_article(), JournalContractStep()]
    allow_early_complete = True
    
    def get_persistence_strategy(self) -> FundingRequestPersistenceStrategy:
        """Override in subclasses to change persistence strategy."""
        return DatabasePersistenceStrategy(self.kwargs["pk"])
    
    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})
    
    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})
    
    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        strategy = self.get_persistence_strategy()
        data = strategy.load_publication_data()
        store.update(data)
        store.save()
    
    def complete(self, **kwargs: Any) -> None:
        store = self.get_store()
        strategy = self.get_persistence_strategy()
        strategy.save_publication_data(store)
```

### DOI Import Wizard (Session Strategy)

```python
class DOIImportUpdatePublicationView(UpdatePublicationView):
    """Update publication data during DOI import preview."""
    
    def get_persistence_strategy(self) -> FundingRequestPersistenceStrategy:
        # Use session strategy instead of database strategy
        return SessionPersistenceStrategy(
            SessionStore("doi_import_draft", self.request)
        )
    
    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:doi_import_preview")
    
    def get_success_url(self) -> str:
        return reverse("fundingrequests:doi_import_preview")
    
    # prepare() and complete() inherited - work automatically!
```

## DOI Import Flow (Revised)

### Phase 1: DOI Input & Fetch

```
POST /import/doi/ with DOI
  ↓
DOIImportService.import_from_doi(doi)
  ↓
Returns CreateFundingRequestDto  # NOT persisted yet!
  ↓
Convert DTO to session storage format:
  session["doi_import_draft"] = {
      "publication_step": dto.publication.to_post_data(...),
      "journal": dto.publication.journal.id,
      "contracts": [...],
      "cost": dto.payment.to_post_data(),
      "funding": [f.to_post_data() for f in dto.funding],
      "extra_information": dto.extra_information.to_post_data(),
  }
  ↓
Redirect → /import/doi/preview/
```

### Phase 2: Preview & Edit

```
GET /import/doi/preview/
  ↓
Load from session["doi_import_draft"]
  ↓
Render detail template (read-only preview)
  ↓
User clicks "Edit Publication"
  ↓
GET /import/doi/edit/publication/
  ↓
DOIImportUpdatePublicationView.prepare():
  - get_adapter() → SessionFundingRequestAdapter
  - adapter.load_publication_data() → loads from session
  - Populates wizard store
  ↓
User edits → POST
  ↓
DOIImportUpdatePublicationView.complete():
  - adapter.save_publication_data(store)
  - Updates session["doi_import_draft"]
  ↓
Redirect → /import/doi/preview/
```

### Phase 3: Final Save

```
POST /import/doi/save/
  ↓
Load session["doi_import_draft"]
  ↓
Reconstruct CreateFundingRequestDto from session
  ↓
fundingrequests.create_fundingrequest(dto)
  ↓
Clear session["doi_import_draft"]
  ↓
Redirect → /fundingrequests/<id>/ (real detail page)
```

## Key Changes from Original Plan

| Original Plan | Revised Approach |
|---------------|------------------|
| Repository pattern for data access | Strategy pattern for wizard persistence |
| Complex serialization of domain objects | Use existing DTO `to_post_data()` methods |
| Service persists immediately | Service returns DTO, persist deferred |
| 3 repository protocols | 1 strategy protocol |
| Session stores domain objects | Session stores DTO post data (existing format) |

## Benefits of Strategy Pattern

1. **Minimal changes to existing wizards** - Just add `get_persistence_strategy()` method
2. **Reuses existing DTO serialization** - No new to_dict/from_dict needed
3. **Clear separation of concerns** - Strategy encapsulates load/save logic
4. **Easy to test** - Mock strategy for wizard tests
5. **Extensible** - Could add FileSystemStrategy, RedisStrategy, etc.
6. **Type safe** - Protocol ensures consistency
7. **Correct pattern name** - Strategy pattern defines a family of interchangeable algorithms

## Implementation Order

### Step 1: Add DTO Preparation Method to DOIImportService ✅ DONE
- ✅ Added `prepare_funding_request_dto()` method - returns DTO without persisting
- ✅ Refactored `import_from_doi()` to call `prepare_funding_request_dto()` then persist
- ✅ Both methods maintained: direct import and DTO preparation
- ✅ Added test for DTO preparation method
- ✅ All 21 tests passing

**Result**: Service now supports both workflows:
- `import_from_doi(doi)` → Direct import with persistence
- `prepare_funding_request_dto(doi)` → Build DTO for preview workflow

### Step 2: Create Strategy Infrastructure
- Define `FundingRequestPersistenceStrategy` protocol
- Implement `DatabasePersistenceStrategy`
- Implement `SessionPersistenceStrategy`
- Add unit tests

### Step 3: Refactor Update Wizards
- Add `get_persistence_strategy()` method to base wizards
- Refactor `prepare()` to use strategy
- Refactor `complete()` to use strategy
- Verify existing functionality unchanged

### Step 4: Build DOI Import UI
- DOI input form view
- Preview view (loads from session)
- Final save view (creates funding request)
- DOI import update wizards (inherit + override `get_persistence_strategy()`)

### Step 5: Testing & Polish
- Integration tests for full flow
- Error handling
- UI polish

## Session Storage Format (Detailed)

```python
session["doi_import_draft"] = {
    # Publication data (for PublicationStep + JournalContractStep)
    "publication_step": {
        "title": "...",
        "license": "CC-BY",
        "publication_state": "Published",
        "online_publication_date": "2024-01-15",
        # ... all fields from PublicationDto.to_post_data()
    },
    "journal": 123,  # JournalId (existing journal) or 0 (new journal)
    "contracts": [
        {"year": 2024, "corresponding_author": true, ...},
    ],
    
    # If journal=0, need attributes to create it
    "journal_attributes": {
        "title": "Nature",
        "eissn": "1476-4687",
        "publisher_id": 456,  # or 0 if publisher also new
    },
    
    # If publisher=0, need attributes to create it
    "publisher_attributes": {
        "name": "Springer Nature",
    },
    
    # Funding data (for FundingStep)
    "cost": {
        "amount": "2500.00",
        "currency": "EUR",
        "method": "invoice",
    },
    "funding": [
        {
            "project_title": "...",
            "percentage": "50.00",
            # ... all fields from ExternalFundingDto.to_post_data()
        },
    ],
    
    # Extra information (for ExtraInformationStep)
    "request_remarks": "...",
    "contact": {
        "name": "...",
        "email": "...",
    },
}
```

## Open Questions

1. **Journal/Publisher creation during edit**: If user changes journal to a new one during edit, do we allow creating journals in preview mode?
   - **Proposal**: Yes, but store as `journal=0` + `journal_attributes` until final save

2. **Detail page preview**: How to render journal/publisher names when they don't exist yet?
   - **Proposal**: Session adapter provides display data alongside IDs

3. **Validation**: Should we validate the entire DTO before allowing save?
   - **Proposal**: Yes, run full DTO validation before final save

## Next Steps

1. **Review this revised approach** - Does the adapter pattern solve the problem?
2. **Decide on DOIImportService return type** - Revert to DTO or keep FundingRequestId?
3. **Prototype adapter implementation** - Validate the approach works
4. **Update implementation plan** - Revise phases and estimates

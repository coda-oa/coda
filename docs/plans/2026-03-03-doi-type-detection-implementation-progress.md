# DOI Type Detection Implementation Progress

**Date:** 2026-03-03  
**Related Design:** `2026-02-17-doi-import-type-detection.md`  
**Current Branch:** `feat/doi-import`

## Current Status: TDD Phase 1 - Expanding Test Coverage

We completed the first TDD cycle with a basic book type test. Now we need to expand test coverage to handle all actual Crossref types before updating the detection logic.

## Actual Crossref Types (from https://api.crossref.org/types)

### Book-like Types (→ Monograph)
- `book`
- `monograph`
- `book-chapter`
- `book-section`
- `book-part`
- `book-track`
- `edited-book`
- `reference-book`
- `reference-entry`
- `dissertation`

### Article-like Types (→ Article)
- `journal-article`
- `proceedings-article`
- `posted-content`
- `peer-review`

### Ambiguous/Other Types (→ Default to Article)
- `report`, `report-component`, `report-series`
- `component`
- `standard`
- `database`, `dataset`
- `grant`
- `other`
- `proceedings`, `proceedings-series`
- `journal`, `journal-volume`, `journal-issue`
- `book-series`, `book-set`

## Updated Detection Logic (To Be Implemented)

```
1. Explicitly book-like Crossref types → Monograph
   (book, monograph, edited-book, book-chapter, book-section, book-part,
    book-track, reference-book, reference-entry, dissertation)

2. Explicitly article-like Crossref types → Article
   (journal-article, proceedings-article, peer-review, posted-content)

3. Has ISBN (but not ISSN) → Monograph

4. Has ISSN (but not ISBN) → Article

5. Has both ISBN and ISSN → Monograph
   (Book chapters in series have both, ISBN is definitive)

6. Ambiguous or unknown types → Article (default)
```

## Implementation TODO List

### ✅ Phase 1.1: Basic Book Detection (COMPLETED)
- [x] Add `isbn` field to `ExternalPublicationMetadata`
- [x] Update Crossref client to extract ISBN
- [x] Add `_detect_publication_type()` method (basic version)
- [x] Add `_build_monograph_dto()` method
- [x] Add `_match_or_create_publisher_for_monograph()` method
- [x] Update `prepare_funding_request_dto()` to use detection
- [x] Write test: `test__prepare_funding_request_dto__book_doi__returns_monograph_dto`
- [x] Update broken test: `test__import_from_doi__metadata_without_journal__raises_invalid_metadata_error`
- [x] All tests pass (22/22)
- [x] Code quality checks pass (ruff, mypy)

### 🔄 Phase 1.2: Comprehensive Type Detection Tests (IN PROGRESS)

**Parametrized Tests:**
- [ ] Write: `test__prepare_funding_request_dto__monograph_types__returns_monograph_dto`
  - Covers: book, monograph, book-chapter, book-section, book-part, book-track, edited-book, reference-book, reference-entry, dissertation
- [ ] Write: `test__prepare_funding_request_dto__article_types__returns_publication_dto`
  - Covers: journal-article, proceedings-article, posted-content, peer-review

**Edge Case Tests:**
- [ ] Write: `test__prepare_funding_request_dto__unknown_type_with_isbn__returns_monograph_dto`
- [ ] Write: `test__prepare_funding_request_dto__unknown_type_with_issn__returns_publication_dto`
- [ ] Write: `test__prepare_funding_request_dto__book_chapter_with_both_isbn_and_issn__returns_monograph_dto`
- [ ] Write: `test__prepare_funding_request_dto__unknown_type_no_identifiers__defaults_to_article`

**Run Tests & Identify Failures:**
- [ ] Run all new tests
- [ ] Document which tests fail (these guide our implementation updates)

### ⏸️ Phase 1.3: Update Detection Logic (PENDING)
- [ ] Update `_detect_publication_type()` to handle all Crossref types
- [ ] Verify all tests pass
- [ ] Update design doc with final detection logic

### ⏸️ Phase 1.4: Commit & Review (PENDING)
- [ ] Run full test suite
- [ ] Run code quality checks (ruff, mypy)
- [ ] Commit with message: "feat(doi-import): add comprehensive article/monograph type detection"
- [ ] Update this progress doc

### ⏸️ Phase 2: UI Override (NOT STARTED)
- [ ] Add radio buttons to `doi_preview_detail.html`
- [ ] Add HTMX endpoint `doi_preview_change_type`
- [ ] Update session storage to track detected_type vs current_type
- [ ] Add warning messages for edge cases

### ⏸️ Phase 3: Journal Modal Integration (DEFERRED)
- [ ] Wait for journal creation modal PR
- [ ] Integrate modal for monograph → article switching

## Current Files Modified

**Production Code:**
- `src/coda/contexts/publication/dto/external_metadata.py` - Added `isbn` field
- `src/coda/contexts/publication/services/doi_client.py` - Added `_extract_isbn()` method
- `src/coda/contexts/publication/services/doi_import_service.py` - Added detection + monograph support

**Test Code:**
- `tests/contexts/publication/test_doi_import_service.py` - Added 1 new test, updated 1 existing test

## Next Immediate Action

Write the parametrized test for monograph types, following TDD approval gates:
1. Request approval to write test
2. Write test
3. Run test to see which scenarios fail
4. Report results
5. Request approval to update implementation

## Notes

- **TDD Rule:** NO production code changes without failing tests first
- **Test Organization:** Separate parametrized tests for monographs vs articles, individual tests for edge cases
- **Crossref Reality Check:** We discovered "book-chapter" IS a real Crossref type (not made up)
- **ISBN Priority:** When both ISBN and ISSN present, ISBN takes precedence (book chapters in series)

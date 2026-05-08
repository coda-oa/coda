# DOI Import: Automatic Article/Monograph Type Detection

**Date:** 2026-02-17  
**Status:** Design - Brainstorming Complete  
**Related:** `2026-02-13-doi-import-final-status.md`

## Overview

The DOI import feature currently only supports importing journal articles. This design extends it to automatically detect and import both articles and monographs (books) based on Crossref metadata, with user override capability.

## Goals

1. **Automatic detection** - Intelligently determine if a DOI represents an article or monograph
2. **User override** - Allow users to switch between article/monograph via UI
3. **Smart switching** - Preserve Crossref metadata to enable seamless type switching
4. **Clear feedback** - Show warnings when metadata is incomplete or ambiguous

## Key Insights from Crossref

### Crossref Metadata Structure

**Journal Articles:**
```json
{
  "type": "journal-article",
  "container-title": ["Nature"],
  "ISSN": ["0028-0836", "1476-4687"],
  "publisher": "Springer Science..."
}
```

**Books/Monographs:**
```json
{
  "type": "book",
  "container-title": [],
  "ISBN": ["9783319184210", "9783319184227"],
  "publisher": "Springer International Publishing"
}
```

**Book Chapters (Important!):**
```json
{
  "type": "book-chapter",
  "container-title": ["Communications in Computer and Information Science"],
  "ISSN": ["1865-0929", "1865-0937"],  // Book SERIES ISSN!
  "ISBN": ["9783319184210"],           // Book ISBN
  "publisher": "Springer"
}
```

**Key Finding:** Books in series can have ISSN (for the series) AND ISBN (for the book). The presence of ISBN is the definitive indicator for books.

## Detection Logic

### Priority Order

```
1. Crossref type = "journal-article"?
   → Article (even if no ISSN - handle in UI)

2. Crossref type = "dissertation"?
   → Monograph (dissertations are book-like)

3. Crossref type in ["book", "monograph", "book-chapter"]?
   → Monograph

4. Has ISBN?
   → Monograph (secondary indicator, catches books with unknown types)

5. Has ISSN (but no ISBN)?
   → Article (catch remaining journals)

6. Default (no clear indicators)?
   → Article (with warning)
```

### Type Categories

**Article Types (from Crossref):**
- `"journal-article"` (primary)
- `"proceedings-article"` (if has ISSN, no ISBN)
- `"report"` (if has ISSN, no ISBN)
- `"posted-content"` (preprints - if has ISSN, no ISBN)

**Monograph Types (from Crossref):**
- `"book"`
- `"monograph"`
- `"book-chapter"`
- `"dissertation"`
- `"edited-book"`

**Ambiguous Types:**
- Use ISBN/ISSN presence as tiebreaker
- Default to Article with warning if neither present

## Edge Cases

### 1. Journal Article with No E-ISSN

**Scenario:** Crossref type = "journal-article", but no E-ISSN (or only print ISSN)

**Handling:**
- Detect as Article
- Show warning: "⚠️ Journal has no E-ISSN. You'll need to select or create the journal manually."
- Provide journal select/create modal
- User can override to Monograph if actually misclassified

**Why:** Our system requires E-ISSN for journal identification. Print-only ISSN is insufficient.

### 2. Book in Series (Has Both ISSN and ISBN)

**Scenario:** Book chapter in series like "Communications in Computer and Information Science"

**Handling:**
- Detect as Monograph (ISBN takes precedence)
- ISSN for series is ignored for type detection
- Publisher extracted from Crossref metadata

**Why:** ISSN represents the book series, not a journal. ISBN is the definitive book indicator.

### 3. Unknown Crossref Type

**Scenario:** Crossref type is null, missing, or unrecognized value

**Handling:**
- Check ISBN → Monograph
- Check ISSN → Article
- Neither → Article (default with warning)

**Warning:** "⚠️ Publication type unclear from Crossref. Defaulting to Article. Please verify."

### 4. Monograph with No Publisher

**Scenario:** Crossref metadata missing publisher name

**Handling:**
- Still detect as Monograph (based on type/ISBN)
- Show error when trying to save: "Publisher required for monographs"
- User must either:
  - Manually enter publisher name
  - Switch to Article (if actually misclassified)

### 5. Type Switching

**Article → Monograph:**
- Have: journal metadata
- Need: publisher
- **Solution:** Extract publisher from Crossref metadata (already present)
- If no publisher in Crossref: Show error, require manual entry

**Monograph → Article:**
- Have: publisher
- Need: journal
- **Solution:** Show journal select/create modal
- User picks existing journal or creates new one
- Extract journal info from Crossref if available (container-title, ISSN)

## Session Storage Strategy

### Session Structure

```python
session[session_key] = {
    # Raw Crossref metadata (for rebuilding DTOs)
    "crossref_metadata": {
        "title": "...",
        "authors": [...],
        "publication_type": "journal-article",
        "journal": {...} or None,
        "publisher": "..." or None,
        "license": "...",
        "online_publication_date": "...",
        "print_publication_date": "...",
    },
    
    # Type detection
    "detected_type": "article",  # What we auto-detected
    "current_type": "article",   # What user currently has selected
    
    # IDs for domain objects
    "journal_id": 123,    # Present if article
    "publisher_id": 456,  # Present if monograph
    
    # Current DTO representation
    "publication": {...},  # PublicationDto or MonographDto
    "payment": {...},
    "funding": [...],
    "extra_information": {...},
    
    # Metadata
    "doi": "10.1234/example",
}
```

### Caching Strategy

1. **Initial fetch:** Store raw `ExternalPublicationMetadata` in session
2. **Type switching:** Rebuild DTO from cached Crossref metadata
3. **Benefit:** No need to cache both article and monograph representations
4. **Trade-off:** Small rebuild cost when switching, but saves session memory

## User Interface Flow

### 1. DOI Input
User enters DOI → Fetch from Crossref → Auto-detect type → Redirect to preview

### 2. Preview Page with Type Override

```
┌─────────────────────────────────────────────┐
│ DOI Import Preview                          │
├─────────────────────────────────────────────┤
│                                             │
│ Import As:                                  │
│   (•) Article (Journal Publication)         │
│   ( ) Monograph (Book)                      │
│                                             │
│ ⚠️ Journal has no E-ISSN. You'll need to   │
│    select or create the journal manually.   │
│                                             │
├─────────────────────────────────────────────┤
│ Publication Details                         │
│ ...                                         │
└─────────────────────────────────────────────┘
```

### 3. Type Switching (HTMX)

**User changes radio button:**
1. HTMX POST to `doi_preview_change_type` endpoint
2. Backend rebuilds DTO from cached Crossref metadata
3. Update session with new type
4. Return updated preview HTML
5. HTMX swaps publication section

**Endpoint:**
```
POST /fundingrequests/doi-preview/<session_key>/change-type/
Body: publication_type=monograph
Response: Updated HTML fragment for publication section
```

## Warnings and Error Messages

### Detection Warnings

**No E-ISSN (Article):**
> ⚠️ Journal has no E-ISSN in Crossref metadata. You'll need to select or create the journal manually before saving.

**No Publisher (Monograph):**
> ⚠️ Publisher information missing from Crossref. You'll need to enter the publisher manually.

**Ambiguous Type:**
> ⚠️ Publication type unclear from Crossref metadata. Defaulting to Article. Please verify using the type selector above.

### Type Switching Errors

**Monograph → Article (No Journal Info):**
> ❌ Cannot switch to Article: No journal information available. Please select or create a journal.
> [Select/Create Journal Button]

**Article → Monograph (No Publisher):**
> ❌ Cannot switch to Monograph: No publisher information available. Please enter publisher name.
> [Publisher Input Field]

## Implementation Notes

### Phase 1: Backend Detection (Current Focus)

1. Update `doi_import_service.py`:
   - Add `_detect_publication_type()` method
   - Return either `PublicationDto` or `MonographDto`
   - Handle both journal and publisher metadata

2. Update session storage:
   - Store raw Crossref metadata
   - Store detected type and current type
   - Store both journal_id and publisher_id when available

3. Update `doi_preview.py` views:
   - Store type information in session
   - Pass type info to template context

### Phase 2: UI Override (Next)

1. Add type selector to `doi_preview_detail.html`
2. Add HTMX endpoint for type switching
3. Add warning messages for edge cases

### Phase 3: Journal Modal Integration (Future)

1. Wait for journal creation modal PR
2. Integrate modal into DOI preview
3. Handle monograph → article switching with modal

## Open Questions

1. **Should we log detection decisions?**
   - Could help debug production issues
   - Could provide analytics on Crossref metadata quality
   - Decision: Punt to future - not critical for MVP

2. **Should we validate publisher name format?**
   - Some publishers have inconsistent naming in Crossref
   - Could auto-correct known variations
   - Decision: Punt to future - handle manually for now

3. **Should we support importing book chapters as separate entities?**
   - Currently treating all books the same
   - Book chapters might need special handling
   - Decision: Treat as monograph for now, revisit if needed

## Testing Strategy

### Test Cases - Detection Logic

1. **Journal article with E-ISSN** → Article ✓
2. **Journal article with only print ISSN** → Article (with warning)
3. **Journal article with no ISSN** → Article (with warning)
4. **Book with ISBN** → Monograph ✓
5. **Book chapter with ISSN and ISBN** → Monograph (ISBN wins) ✓
6. **Dissertation** → Monograph ✓
7. **Proceedings article with ISSN** → Article
8. **Unknown type with ISBN** → Monograph
9. **Unknown type with ISSN** → Article
10. **Unknown type with neither** → Article (with warning)

### Test Cases - Type Switching

1. **Article → Monograph with publisher in Crossref** → Success
2. **Article → Monograph without publisher** → Error message
3. **Monograph → Article with journal info** → Show modal
4. **Monograph → Article without journal info** → Show modal
5. **Switch back and forth** → Preserves metadata

### Test Cases - Edge Cases

1. **Book in series (ISSN + ISBN)** → Correctly detects as Monograph
2. **E-ISSN required for article** → Shows warning, allows manual journal selection
3. **Missing Crossref type** → Uses ISBN/ISSN as fallback
4. **Null/empty metadata fields** → Handles gracefully

## Success Criteria

- [x] Detection logic designed with priority order
- [x] Edge cases identified and handling defined
- [x] Session storage strategy defined
- [x] UI flow designed with HTMX
- [ ] Backend implementation complete
- [ ] Frontend implementation complete
- [ ] Tests passing for all cases
- [ ] Journal modal integration complete

## Future Enhancements

1. **Smart publisher matching** - Use fuzzy matching for publisher names
2. **Book chapter handling** - Special treatment for chapters vs full books
3. **Series detection** - Recognize and track book series
4. **Metadata enrichment** - Fetch additional data from other sources
5. **Detection analytics** - Track which detection rules are most common

## Related Documentation

- **DOI Import Overview:** `docs/plans/2026-02-13-doi-import-final-status.md`
- **Crossref API:** https://api.crossref.org/
- **Crossref Types:** https://api.crossref.org/types

---

**Next Steps:** Move to implementation phase - start with backend detection logic.

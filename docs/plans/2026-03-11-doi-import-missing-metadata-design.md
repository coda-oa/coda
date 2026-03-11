# DOI Import — Missing Metadata Recovery Design

## Overview

When Crossref metadata is missing a journal (for articles) or publisher (for monographs),
the DOI import currently raises `InvalidMetadataError`, resulting in an unhandled error on
the input page. This feature lets users recover by showing the preview page with all
available data plus a warning, with the relevant fix form (journal or publisher search)
auto-opened so they can supply the missing piece themselves.

## Goals

- Never crash on missing journal/publisher metadata — always reach the preview page
- Warn the user clearly about what is missing and where to fix it
- Auto-open the relevant type-selector form so the fix is one click away
- Warning disappears once the user applies an override (journal or publisher selected)
- No new URL endpoints, no session schema changes, no public API changes

## Approach

Warnings are computed as a `@property` on `PreviewArticle` and `PreviewMonograph` from
their existing fields. `PreviewFundingRequest` delegates to its nested publication.
No new stored state — warnings are derived at access time from data already present.

The mapping functions (`build_preview_article`, `build_preview_monograph`) stop raising
`InvalidMetadataError` for missing journal/publisher and instead let the `None` values
through. The DTO's property handles communicating the gap to the view layer.

`build_preview_context` is simplified: its signature changes to accept a live
`PreviewFundingRequest` directly (removing the wasteful `model_dump` → `model_validate`
round-trip), dead weight related to costs/funding is removed, and `"warnings"` is added
to the returned context dict.

The preview template is also cleaned up: the `costs_funding_section.html` include is
removed (it is only needed on the full detail page after saving). Warnings are rendered
as a banner above the type-selector. When warnings are present, the relevant fix form
partial is rendered inline on the server side — no client-side HTMX trigger needed.

## Architecture

```
Crossref metadata (journal=None or publisher=None)
    │
    ▼
build_preview_article / build_preview_monograph
    │  (no longer raises — passes None through)
    ▼
PreviewArticle.warnings / PreviewMonograph.warnings
    │  (@property, derived from fields)
    ▼
PreviewFundingRequest.warnings
    │  (delegates to publication.warnings)
    ▼
build_preview_context(preview_fr, session_key)
    │  (adds "warnings" to context dict)
    ▼
doi_preview_detail.html
    │  (renders warning banner + auto-opens fix form if warnings present)
    ▼
User selects journal/publisher → applies override
    │  (override resolves the gap → warnings = [])
    ▼
Warning disappears on next preview render
```

## Components

### `PreviewArticle` (dto/preview.py)
- `journal: PreviewJournal | None` — already nullable in the external metadata source;
  type annotation updated to reflect this
- `@property warnings(self) -> list[str]` — returns
  `["Journal metadata missing from Crossref — please select a journal below."]`
  if `journal is None`, else `[]`

### `PreviewMonograph` (dto/preview.py)
- `publisher_name: str | None` — already nullable; no type change needed
- `@property warnings(self) -> list[str]` — returns
  `["Publisher metadata missing from Crossref — please select a publisher below."]`
  if `publisher_name is None`, else `[]`

### `PreviewFundingRequest` (dto/preview.py)
- `@property warnings(self) -> list[str]` — delegates to `self.publication.warnings`

### `build_preview_article` (_metadata_mapping.py)
- Remove `if metadata.journal is None: raise InvalidMetadataError(...)` guard
- Pass `metadata.journal` (possibly `None`) directly to `PreviewArticle`

### `build_preview_monograph` (_metadata_mapping.py)
- Remove `if metadata.publisher is None: raise InvalidMetadataError(...)` guard
- Pass `metadata.publisher` (possibly `None`) directly to `PreviewMonograph`

### `build_preview_context` (queries/preview_context_builder.py)
- Signature: `(preview_fr: PreviewFundingRequest, session_key: str) -> dict`
  (was `session_data: dict`)
- Remove `PreviewFundingRequest.model_validate(session_data)` — use `preview_fr` directly
- Remove: `payment`, `funding_request`, `external_funding`, `contact`,
  `_convert_preview_publication_to_domain` — all fed only the costs/funding section
- Add `"warnings": preview_fr.warnings` to returned context dict

### `DOIPreviewDetailView.get` (views/doi_preview.py)
- Pass `preview_dto` directly to `build_preview_context` instead of
  `preview_dto.model_dump(mode="json")`

### `doi_preview_detail.html`
- Remove `{% include "fundingrequests/partials/costs_funding_section.html" %}`
- Add warning banner: `{% for warning in warnings %}<p ...>{{ warning }}</p>{% endfor %}`
- When `warnings` is non-empty, include the appropriate fix form partial inline
  (article → `doi_type_change_to_article.html`, monograph → `doi_type_change_to_monograph.html`)
  so the form is server-rendered on first load without any HTMX trigger

## Data Flow

**Missing journal (article):**
1. Crossref returns `journal: null` for a journal-article DOI
2. `build_preview_article` passes `journal=None` to `PreviewArticle`
3. `PreviewArticle.warnings` → `["Journal metadata missing..."]`
4. Preview page renders warning banner + journal search form pre-opened
5. User searches and selects a journal, clicks Apply
6. Session stores `journal_id`, `publication_type: "article"`
7. `build_preview_with_type_override` resolves journal from DB → `journal` is not `None`
8. `PreviewArticle.warnings` → `[]` → warning banner does not render

**Missing publisher (monograph):**
1. Crossref returns `publisher: null` for a monograph DOI
2. `build_preview_monograph` passes `publisher_name=None` to `PreviewMonograph`
3. `PreviewMonograph.warnings` → `["Publisher metadata missing..."]`
4. Preview page renders warning banner + publisher search form pre-opened
5. User searches and selects a publisher, clicks Apply
6. Session stores `publisher_id`, `publication_type: "monograph"`
7. `build_preview_with_type_override` resolves publisher from DB → `publisher_name` is not `None`
8. `PreviewMonograph.warnings` → `[]` → warning banner does not render

## Error Handling

`InvalidMetadataError` is no longer raised by `build_preview_article` or
`build_preview_monograph` for missing journal/publisher. It is still raised in
`_match_or_create_journal` (missing journal title, missing publisher name on new journal)
and `_convert_preview_to_creation_dto` (missing E-ISSN) — these are save-time errors
that the user cannot pre-emptively fix via the preview UI.

## Testing Strategy

Tests are focused on the two public API surfaces:

### `DOIImportService.fetch_doi_preview`
- When article metadata has `journal=None`: returns `PreviewFundingRequest` with
  non-empty `warnings` (no exception raised)
- When monograph metadata has `publisher=None`: returns `PreviewFundingRequest` with
  non-empty `warnings` (no exception raised)
- Update any existing tests that assert `InvalidMetadataError` is raised for these cases

### `DOIPreviewDetailView`
- When session metadata has missing journal: preview page returns 200, `warnings` in
  context is non-empty, journal fix form is rendered inline
- When session metadata has missing publisher: preview page returns 200, `warnings` in
  context is non-empty, publisher fix form is rendered inline
- When override is applied (journal or publisher selected): preview page returns 200,
  `warnings` in context is empty

## Implementation Notes

- `PreviewArticle.journal` type annotation changes from `PreviewJournal` to
  `PreviewJournal | None`. Check all call sites that access `preview_article.journal`
  (e.g. `_build_publication_detail_from_preview`) and add `None` guards where needed —
  display `""` or `"Unknown"` for missing journal fields in `PublicationDetail`
- `build_preview_context` removal of `_convert_preview_publication_to_domain` also
  removes the `FundingRequest` domain object construction — verify no other template
  or view depends on `funding_request` being in the preview context
- The inline fix form on the preview page reuses the same partials
  (`doi_type_change_to_article.html`, `doi_type_change_to_monograph.html`) already
  used by the HTMX type-change flow — no new templates needed

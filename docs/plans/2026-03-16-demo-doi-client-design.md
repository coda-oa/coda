# Demo DOI Client Design

## Overview

Swap the real Crossref API client for an in-memory fake when running in demo mode, to avoid consuming rate-limited Crossref API calls in the public demo environment.

## Goals

1. **Protect Crossref API quota** — demo users never hit the real API
2. **Realistic demo experience** — a curated set of real DOIs returns rich, accurate metadata
3. **No view-layer leakage** — views remain unaware of demo mode
4. **Reuse test infrastructure** — the same fake client used in tests serves demo mode

## Approach

### Why `InMemoryDOIMetadataClient` in `fakes.py`

The existing `FakeDOIMetadataClient` in `tests/` already implements the `DOIMetadataClient` Protocol and supports per-DOI data and error configuration. Rather than creating a parallel `DemoDoiClient`, we promote this class to a first-class production fake in `src/`, add a `from_json()` constructor, and rename it to `InMemoryDOIMetadataClient` to reflect that it is not test-specific.

This eliminates duplication: tests import from `fakes.py`, and demo mode uses the same class loaded from a fixture file.

### Why `AppConfig.ready()` for wiring

`AppConfig.ready()` is Django's documented hook for startup initialisation. Reading `settings.CODA_DEMO_MODE` there and assigning to the `ClassVar` on each view is the established Django idiom — zero per-request overhead, works in all execution contexts (WSGI, ASGI, management commands), and is fully testable via `@override_settings`.

Third-party feature flag libraries (django-waffle, django-flags) would add unnecessary complexity: we don't need runtime toggling, per-user flags, or multi-condition logic. A settings boolean is the right tool.

### Why `DOINotFoundError` (not a new exception) for unknown demo DOIs

Views already handle `DOINotFoundError` from the real client. Raising the same error from `InMemoryDOIMetadataClient` for an unknown DOI keeps the view clean — it doesn't need to know *why* a DOI wasn't found. A descriptive message (`"This DOI is not available in the demo dataset"`) is carried on the exception so the user still gets meaningful feedback.

## Architecture

```
src/coda/
  contexts/publication/services/
    doi_client.py               # DOIMetadataClient Protocol + CrossrefDoiClient (unchanged)
    fakes.py                    # NEW: InMemoryDOIMetadataClient
  fixtures/
    demo_dois.json              # NEW: ~10 curated DOIs (articles + monographs)
  apps/fundingrequests/
    apps.py                     # MODIFIED: ready() wires InMemoryDOIMetadataClient on CODA_DEMO_MODE

tests/
  contexts/publication/
    fixtures/doi_client.py      # MODIFIED: import InMemoryDOIMetadataClient from fakes.py
  contexts/publication/services/
    test_in_memory_doi_client.py  # NEW
  apps/fundingrequests/
    test_demo_mode.py             # NEW
```

No changes to: `errors.py`, `doi_preview.py`, `CrossrefDoiClient`, `DOIImportService`.

## Components

### `InMemoryDOIMetadataClient` (`services/fakes.py`)

Implements `DOIMetadataClient`. Holds metadata and error configuration in memory.

```python
class InMemoryDOIMetadataClient:
    def __init__(self) -> None:
        self.data: dict[str, ExternalPublicationMetadata] = {}
        self._errors: dict[str, ErrorType] = {}

    @staticmethod
    def from_json(path: Path) -> "InMemoryDOIMetadataClient":
        """Load and validate a JSON fixture file at startup."""
        client = InMemoryDOIMetadataClient()
        raw = json.loads(path.read_text())
        client.data = {
            doi: ExternalPublicationMetadata.model_validate(meta)
            for doi, meta in raw.items()
        }
        return client

    def configure_error(self, doi: Doi, error_type: ErrorType) -> None:
        """Configure a DOI to raise a specific error. Used in tests."""

    def fetch(self, doi: Doi) -> ExternalPublicationMetadata:
        # 1. Check _errors — raise configured error if present
        # 2. Check data — return metadata if present
        # 3. Miss → raise DOINotFoundError("This DOI is not available in the demo dataset")
```

Validation via `model_validate()` in `from_json()` means a malformed fixture causes a loud startup failure rather than a silent bad response at request time.

### `demo_dois.json` (`src/coda/fixtures/demo_dois.json`)

~10 entries keyed by DOI string. Values are `ExternalPublicationMetadata` objects serialised with `.model_dump()`. Covers:
- ~5 journal articles (with authors, affiliations, ROR IDs, ISSNs, license)
- ~5 monographs (with ISBNs, editors, publishers)

### `FundingRequestsConfig.ready()` (`apps.py`)

```python
def ready(self) -> None:
    from django.conf import settings
    if getattr(settings, "CODA_DEMO_MODE", False):
        from pathlib import Path
        from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient
        from coda.apps.fundingrequests.views.doi_preview import (
            DOIImportInputView, DOIPreviewDetailView, DOIPreviewSaveView,
        )
        client = InMemoryDOIMetadataClient.from_json(
            Path(settings.BASE_DIR) / "src/coda/fixtures/demo_dois.json"
        )
        DOIImportInputView.doi_client = client
        DOIPreviewDetailView.doi_client = client
        DOIPreviewSaveView.doi_client = client
```

## Data Flow

**Known DOI (demo mode on):**
```
User submits DOI → DOIImportInputView.post()
  → InMemoryDOIMetadataClient.fetch(doi)
  → dict lookup → hit
  → ExternalPublicationMetadata returned
  → DOIImportService processes metadata (unchanged)
  → preview rendered
```

**Unknown DOI (demo mode on):**
```
User submits DOI → DOIImportInputView.post()
  → InMemoryDOIMetadataClient.fetch(doi)
  → dict lookup → miss
  → raises DOINotFoundError("This DOI is not available in the demo dataset")
  → view catches DOINotFoundError (existing handler)
  → input form rendered with error message
```

**Startup:**
```
django.setup() → FundingRequestsConfig.ready()
  → CODA_DEMO_MODE is True
  → InMemoryDOIMetadataClient.from_json(demo_dois.json)
    → JSON loaded, each entry validated via model_validate()
  → assigned to ClassVar on all three views
  → CrossrefDoiClient never instantiated
```

## Testing Strategy

### Existing tests — no behaviour changes
Only the import path changes in `tests/contexts/publication/fixtures/doi_client.py`:
```python
# before
from tests.contexts.publication.fixtures.doi_client import FakeDOIMetadataClient
# after
from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient
```
All fixtures and test logic remain identical.

### New unit tests (`test_in_memory_doi_client.py`)
- `fetch()` returns correct metadata for a known DOI
- `fetch()` raises `DOINotFoundError` for an unknown DOI
- `fetch()` raises the configured error when `configure_error()` is set
- `from_json()` loads and validates a valid fixture correctly
- `from_json()` raises on malformed JSON or invalid `ExternalPublicationMetadata`

### New integration tests (`test_demo_mode.py`)
- `@override_settings(CODA_DEMO_MODE=True)` → all three views have `doi_client` set to `InMemoryDOIMetadataClient` after `ready()`
- `@override_settings(CODA_DEMO_MODE=False)` → views retain `CrossrefDoiClient`

## Implementation Notes

- The `from_json()` static constructor is the only entry point for demo mode — tests continue to use `__init__()` and configure data directly
- `configure_error()` is retained for test use; demo mode never calls it
- `fakes.py` lives in `src/` (production-importable) but the name intentionally signals it is a test double — this is an accepted pattern for fakes that serve both tests and non-production environments
- The fixture path is resolved relative to `settings.BASE_DIR` to work correctly in all environments (local, Docker, CI)

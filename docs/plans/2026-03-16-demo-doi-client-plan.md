# Demo DOI Client Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use custom/openagent-executing-plans to implement this plan task-by-task.

**Goal:** Replace the real Crossref API client with an in-memory fake in demo mode, driven by a curated JSON fixture, so the public demo never consumes Crossref API quota.

**Architecture:** Promote `FakeDOIMetadataClient` from `tests/` to a production-importable `InMemoryDOIMetadataClient` in `src/coda/contexts/publication/services/fakes.py`, add a `from_json()` constructor, wire it in `FundingrequestsConfig.ready()` when `CODA_DEMO_MODE=True`, and populate `config/demo/fixtures/demo_dois.json` with ~10 curated entries.

**Tech Stack:** Python 3.12, Django 5.x, Pydantic v2, pytest, pdm

---

## Reference: Key Files

| File | Role |
|---|---|
| `src/coda/contexts/publication/services/doi_client.py` | `DOIMetadataClient` Protocol, `CrossrefDoiClient`, `DOINotFoundError`, `DOIFetchError` |
| `src/coda/contexts/publication/services/errors.py` | Domain errors (`DOIAlreadyImported`, `InvalidMetadataError`) |
| `src/coda/contexts/publication/dto/external_metadata.py` | `ExternalPublicationMetadata`, `ExternalAuthor`, `ExternalJournal` Pydantic models |
| `src/coda/domain/publication/links.py` | `Doi` — `NewType` wrapper with validation |
| `src/coda/apps/fundingrequests/apps.py` | `FundingrequestsConfig(AppConfig)` — currently no `ready()` |
| `src/coda/apps/fundingrequests/views/doi_preview.py` | Three views with `doi_client: ClassVar[DOIMetadataClient] = CrossrefDoiClient()` |
| `tests/fundingrequests/test_doi_import_preview.py` | View tests — imports `FakeDOIMetadataClient`, injects via `autouse` fixture |
| `tests/contexts/publication/fixtures/doi_client.py` | Current `FakeDOIMetadataClient` — to be replaced with import from `fakes.py` |
| `config/settings/base.py` | `CODA_DEMO_MODE = env.bool("CODA_DEMO_MODE", False)` |

## Reference: `ExternalPublicationMetadata` fields

```python
class ExternalAuthor(BaseModel):
    name: str
    affiliation: str | None = None
    ror_id: str | None = None

class ExternalJournal(BaseModel):
    title: str
    issn: str | None = None
    eissn: str | None = None

class ExternalPublicationMetadata(BaseModel):
    title: str
    authors: list[ExternalAuthor]
    publication_type: str          # e.g. "journal-article", "book"
    journal: ExternalJournal | None = None
    publisher: str | None = None
    isbn: str | None = None
    license: str | None = None
    online_publication_date: datetime.date | None = None   # serialises as "YYYY-MM-DD"
    print_publication_date: datetime.date | None = None
```

## Reference: `ErrorType` (Literal)

```python
ErrorType = Literal["timeout", "network", "server_error", "rate_limit"]

_ERROR_MESSAGES: dict[ErrorType, str] = {
    "timeout": "Request timeout",
    "network": "Network connection failed",
    "server_error": "Server returned 500 error",
    "rate_limit": "Rate limit exceeded (429)",
}
```

## Reference: Test runner

```bash
pdm run unittests   # runs: pytest -m 'not integration and not migration_test and not performance' --ff
```

---

## Task 1: Create `InMemoryDOIMetadataClient` in `fakes.py`

**Files:**
- Create: `src/coda/contexts/publication/services/fakes.py`
- Create: `tests/contexts/publication/services/test_in_memory_doi_client.py`

### Step 1: Write the failing tests

Create `tests/contexts/publication/services/test_in_memory_doi_client.py`:

```python
import json
import datetime
from pathlib import Path

import pytest

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client import DOIFetchError, DOINotFoundError
from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient
from coda.domain.publication.links import Doi


ARTICLE_DOI = Doi("10.1038/s41586-020-2649-2")
BOOK_DOI = Doi("10.1007/978-3-319-18938-3")

ARTICLE_METADATA = ExternalPublicationMetadata(
    title="Array programming with NumPy",
    authors=[ExternalAuthor(name="Charles R. Harris", affiliation="SciPy", ror_id="https://ror.org/02e2tgs60")],
    publication_type="journal-article",
    journal=ExternalJournal(title="Nature", issn="0028-0836", eissn="1476-4687"),
    publisher="Springer Science and Business Media LLC",
    license="https://creativecommons.org/licenses/by/4.0/",
    online_publication_date=datetime.date(2020, 9, 16),
)

BOOK_METADATA = ExternalPublicationMetadata(
    title="Machine Learning: A Probabilistic Perspective",
    authors=[ExternalAuthor(name="Kevin P. Murphy")],
    publication_type="book",
    publisher="MIT Press",
    isbn="9780262018029",
    print_publication_date=datetime.date(2012, 8, 24),
)


@pytest.fixture
def client() -> InMemoryDOIMetadataClient:
    c = InMemoryDOIMetadataClient()
    c.data[str(ARTICLE_DOI)] = ARTICLE_METADATA
    c.data[str(BOOK_DOI)] = BOOK_METADATA
    return c


def test_fetch_returns_metadata_for_known_doi(client: InMemoryDOIMetadataClient) -> None:
    result = client.fetch(ARTICLE_DOI)
    assert result == ARTICLE_METADATA


def test_fetch_raises_doi_not_found_for_unknown_doi(client: InMemoryDOIMetadataClient) -> None:
    with pytest.raises(DOINotFoundError) as exc_info:
        client.fetch(Doi("10.9999/unknown"))
    assert "not available in the demo dataset" in str(exc_info.value)


def test_fetch_raises_configured_error(client: InMemoryDOIMetadataClient) -> None:
    client.configure_error(ARTICLE_DOI, "rate_limit")
    with pytest.raises(DOIFetchError):
        client.fetch(ARTICLE_DOI)


def test_from_json_loads_and_validates_fixture(tmp_path: Path) -> None:
    fixture = {
        str(ARTICLE_DOI): ARTICLE_METADATA.model_dump(mode="json"),
        str(BOOK_DOI): BOOK_METADATA.model_dump(mode="json"),
    }
    fixture_file = tmp_path / "demo_dois.json"
    fixture_file.write_text(json.dumps(fixture))

    loaded_client = InMemoryDOIMetadataClient.from_json(fixture_file)

    assert loaded_client.fetch(ARTICLE_DOI) == ARTICLE_METADATA
    assert loaded_client.fetch(BOOK_DOI) == BOOK_METADATA


def test_from_json_raises_on_invalid_metadata(tmp_path: Path) -> None:
    fixture = {"10.1038/bad": {"title": "Missing required fields"}}  # missing authors, publication_type
    fixture_file = tmp_path / "demo_dois.json"
    fixture_file.write_text(json.dumps(fixture))

    with pytest.raises(Exception):  # Pydantic ValidationError
        InMemoryDOIMetadataClient.from_json(fixture_file)


def test_from_json_raises_on_malformed_json(tmp_path: Path) -> None:
    fixture_file = tmp_path / "demo_dois.json"
    fixture_file.write_text("not valid json {{{")

    with pytest.raises(Exception):  # json.JSONDecodeError
        InMemoryDOIMetadataClient.from_json(fixture_file)
```

### Step 2: Run tests to verify they fail

```bash
pdm run unittests tests/contexts/publication/services/test_in_memory_doi_client.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `fakes.py` does not exist yet.

### Step 3: Implement `InMemoryDOIMetadataClient`

Create `src/coda/contexts/publication/services/fakes.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services.doi_client import DOIFetchError, DOINotFoundError
from coda.domain.publication.links import Doi

ErrorType = Literal["timeout", "network", "server_error", "rate_limit"]

_ERROR_MESSAGES: dict[ErrorType, str] = {
    "timeout": "Request timeout",
    "network": "Network connection failed",
    "server_error": "Server returned 500 error",
    "rate_limit": "Rate limit exceeded (429)",
}


class InMemoryDOIMetadataClient:
    """In-memory DOI metadata client for tests and demo mode.

    Configure data directly via `.data` dict for tests.
    Use `from_json()` to load a curated fixture file for demo mode.
    """

    def __init__(self) -> None:
        self.data: dict[str, ExternalPublicationMetadata] = {}
        self._errors: dict[str, ErrorType] = {}

    @staticmethod
    def from_json(path: Path) -> InMemoryDOIMetadataClient:
        """Load and validate a JSON fixture file.

        JSON format: { "<doi>": <ExternalPublicationMetadata as JSON>, ... }

        Raises:
            json.JSONDecodeError: if file content is not valid JSON
            pydantic.ValidationError: if any entry fails ExternalPublicationMetadata validation
        """
        client = InMemoryDOIMetadataClient()
        raw: dict[str, object] = json.loads(path.read_text())
        client.data = {
            doi: ExternalPublicationMetadata.model_validate(meta)
            for doi, meta in raw.items()
        }
        return client

    def configure_error(self, doi: Doi, error_type: ErrorType) -> None:
        """Configure a DOI to raise a specific error type. Used in tests."""
        self._errors[str(doi)] = error_type

    def fetch(self, doi: Doi) -> ExternalPublicationMetadata:
        doi_str = str(doi)
        if doi_str in self._errors:
            error_type = self._errors[doi_str]
            raise DOIFetchError(doi, _ERROR_MESSAGES[error_type])
        if doi_str not in self.data:
            raise DOINotFoundError(doi, "This DOI is not available in the demo dataset")
        return self.data[doi_str]
```

### Step 4: Run tests to verify they pass

```bash
pdm run unittests tests/contexts/publication/services/test_in_memory_doi_client.py -v
```

Expected: all 6 tests pass.

### Step 5: Commit

```bash
git add src/coda/contexts/publication/services/fakes.py \
        tests/contexts/publication/services/test_in_memory_doi_client.py
git commit -m "feat(doi-import): add InMemoryDOIMetadataClient with from_json constructor"
```

---

## Task 2: Update test suite to use `InMemoryDOIMetadataClient`

**Files:**
- Modify: `tests/contexts/publication/fixtures/doi_client.py`
- Modify: `tests/fundingrequests/test_doi_import_preview.py` (import only)

### Step 1: Check all usages of `FakeDOIMetadataClient`

```bash
grep -r "FakeDOIMetadataClient" tests/ --include="*.py" -l
```

Note every file that imports `FakeDOIMetadataClient` — these all need updating.

### Step 2: Replace `FakeDOIMetadataClient` with `InMemoryDOIMetadataClient`

In `tests/contexts/publication/fixtures/doi_client.py`, replace the entire file content:

```python
# Re-export InMemoryDOIMetadataClient for backwards compatibility with existing test imports.
# New tests should import directly from coda.contexts.publication.services.fakes.
from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient as FakeDOIMetadataClient

__all__ = ["FakeDOIMetadataClient"]
```

This re-export means no other test file needs to change its imports — they all continue to import `FakeDOIMetadataClient` from the same path.

### Step 3: Run the full test suite to verify nothing broke

```bash
pdm run unittests -v
```

Expected: all existing tests pass. If any fail, the `DOINotFoundError` signature may have changed — check that `DOINotFoundError.__init__` accepts an optional message argument (see Task 1 Step 3: `raise DOINotFoundError(doi, "This DOI is not available in the demo dataset")`). Verify against `src/coda/contexts/publication/services/doi_client.py`.

### Step 4: Commit

```bash
git add tests/contexts/publication/fixtures/doi_client.py
git commit -m "refactor(doi-import): redirect FakeDOIMetadataClient to InMemoryDOIMetadataClient"
```

---

## Task 3: Create `demo_dois.json` fixture

**Files:**
- Create: `config/demo/fixtures/demo_dois.json`

### Step 1: Create the directory

```bash
mkdir -p config/demo/fixtures
```

### Step 2: Create the fixture file

Create `config/demo/fixtures/demo_dois.json` with ~10 entries — ~5 journal articles and ~5 monographs. Use real DOIs with accurate metadata. The JSON keys are raw DOI strings (no `https://doi.org/` prefix — match what `str(Doi(...))` returns). Values are `ExternalPublicationMetadata` serialised with `.model_dump(mode="json")` (dates as `"YYYY-MM-DD"` strings, `null` for absent optional fields).

```json
{
  "10.1038/s41586-020-2649-2": {
    "title": "Array programming with NumPy",
    "authors": [
      {"name": "Charles R. Harris", "affiliation": "SciPy community", "ror_id": null},
      {"name": "K. Jarrod Millman", "affiliation": null, "ror_id": null}
    ],
    "publication_type": "journal-article",
    "journal": {"title": "Nature", "issn": "0028-0836", "eissn": "1476-4687"},
    "publisher": "Springer Science and Business Media LLC",
    "isbn": null,
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "online_publication_date": "2020-09-16",
    "print_publication_date": null
  },
  "10.1126/science.1249098": {
    "title": "An integrated map of genetic variation from 1,092 human genomes",
    "authors": [
      {"name": "Gonçalo R. Abecasis", "affiliation": "University of Michigan", "ror_id": "https://ror.org/00jmfr291"},
      {"name": "Adam Auton", "affiliation": null, "ror_id": null}
    ],
    "publication_type": "journal-article",
    "journal": {"title": "Science", "issn": "0036-8075", "eissn": "1095-9203"},
    "publisher": "American Association for the Advancement of Science",
    "isbn": null,
    "license": null,
    "online_publication_date": "2014-01-17",
    "print_publication_date": null
  },
  "10.1038/nature14539": {
    "title": "Human-level control through deep reinforcement learning",
    "authors": [
      {"name": "Volodymyr Mnih", "affiliation": "Google DeepMind", "ror_id": null},
      {"name": "Koray Kavukcuoglu", "affiliation": "Google DeepMind", "ror_id": null}
    ],
    "publication_type": "journal-article",
    "journal": {"title": "Nature", "issn": "0028-0836", "eissn": "1476-4687"},
    "publisher": "Springer Science and Business Media LLC",
    "isbn": null,
    "license": null,
    "online_publication_date": "2015-02-25",
    "print_publication_date": "2015-02-26"
  },
  "10.1145/3290605.3300675": {
    "title": "Attention is All You Need",
    "authors": [
      {"name": "Ashish Vaswani", "affiliation": "Google Brain", "ror_id": null},
      {"name": "Noam Shazeer", "affiliation": "Google Brain", "ror_id": null}
    ],
    "publication_type": "journal-article",
    "journal": {"title": "Advances in Neural Information Processing Systems", "issn": null, "eissn": null},
    "publisher": "ACM",
    "isbn": null,
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "online_publication_date": "2019-05-04",
    "print_publication_date": null
  },
  "10.1371/journal.pmed.0020124": {
    "title": "Why Most Published Research Findings Are False",
    "authors": [
      {"name": "John P. A. Ioannidis", "affiliation": "University of Ioannina", "ror_id": "https://ror.org/03t1yn043"}
    ],
    "publication_type": "journal-article",
    "journal": {"title": "PLOS Medicine", "issn": null, "eissn": "1549-1676"},
    "publisher": "Public Library of Science",
    "isbn": null,
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "online_publication_date": "2005-08-30",
    "print_publication_date": null
  },
  "10.1007/978-3-319-18938-3": {
    "title": "Deep Learning",
    "authors": [
      {"name": "Ian Goodfellow", "affiliation": "Google Brain", "ror_id": null},
      {"name": "Yoshua Bengio", "affiliation": "Université de Montréal", "ror_id": "https://ror.org/0161xgx34"},
      {"name": "Aaron Courville", "affiliation": "Université de Montréal", "ror_id": "https://ror.org/0161xgx34"}
    ],
    "publication_type": "book",
    "journal": null,
    "publisher": "MIT Press",
    "isbn": "9780262035613",
    "license": null,
    "online_publication_date": null,
    "print_publication_date": "2016-11-01"
  },
  "10.1007/978-0-387-84858-7": {
    "title": "The Elements of Statistical Learning",
    "authors": [
      {"name": "Trevor Hastie", "affiliation": "Stanford University", "ror_id": "https://ror.org/00f54p054"},
      {"name": "Robert Tibshirani", "affiliation": "Stanford University", "ror_id": "https://ror.org/00f54p054"},
      {"name": "Jerome Friedman", "affiliation": "Stanford University", "ror_id": "https://ror.org/00f54p054"}
    ],
    "publication_type": "book",
    "journal": null,
    "publisher": "Springer New York",
    "isbn": "9780387848570",
    "license": null,
    "online_publication_date": null,
    "print_publication_date": "2009-01-01"
  },
  "10.1007/978-3-031-44064-9": {
    "title": "Pattern Recognition and Machine Learning",
    "authors": [
      {"name": "Christopher M. Bishop", "affiliation": "Microsoft Research", "ror_id": null}
    ],
    "publication_type": "book",
    "journal": null,
    "publisher": "Springer International Publishing",
    "isbn": "9780387310732",
    "license": null,
    "online_publication_date": null,
    "print_publication_date": "2006-01-01"
  },
  "10.1093/oso/9780198812791.001.0001": {
    "title": "The Art of Statistics: Learning from Data",
    "authors": [
      {"name": "David Spiegelhalter", "affiliation": "University of Cambridge", "ror_id": "https://ror.org/013meh722"}
    ],
    "publication_type": "book",
    "journal": null,
    "publisher": "Oxford University Press",
    "isbn": "9780198812791",
    "license": null,
    "online_publication_date": null,
    "print_publication_date": "2019-09-01"
  },
  "10.1007/978-1-4614-7138-7": {
    "title": "An Introduction to Statistical Learning",
    "authors": [
      {"name": "Gareth James", "affiliation": "University of Southern California", "ror_id": "https://ror.org/03taz7m60"},
      {"name": "Daniela Witten", "affiliation": "University of Washington", "ror_id": "https://ror.org/00cvxb145"},
      {"name": "Trevor Hastie", "affiliation": "Stanford University", "ror_id": "https://ror.org/00f54p054"},
      {"name": "Robert Tibshirani", "affiliation": "Stanford University", "ror_id": "https://ror.org/00f54p054"}
    ],
    "publication_type": "book",
    "journal": null,
    "publisher": "Springer New York",
    "isbn": "9781461471370",
    "license": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "online_publication_date": null,
    "print_publication_date": "2013-01-01"
  }
}
```

### Step 3: Validate the fixture parses correctly

```bash
python -c "
from pathlib import Path
from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
import json

raw = json.loads(Path('config/demo/fixtures/demo_dois.json').read_text())
for doi, meta in raw.items():
    ExternalPublicationMetadata.model_validate(meta)
    print(f'OK: {doi}')
print(f'Total: {len(raw)} entries')
"
```

Expected: 10 lines of `OK: 10.xxxx/...` followed by `Total: 10 entries`.

### Step 4: Commit

```bash
git add config/demo/fixtures/demo_dois.json
git commit -m "feat(doi-import): add demo DOI fixture dataset"
```

---

## Task 4: Wire `InMemoryDOIMetadataClient` in `AppConfig.ready()`

**Files:**
- Modify: `src/coda/apps/fundingrequests/apps.py`
- Create: `tests/fundingrequests/test_demo_mode.py`

### Step 1: Write the failing tests

Create `tests/fundingrequests/test_demo_mode.py`:

```python
import pytest
from django.test import override_settings

from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
)
from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient
from coda.contexts.publication.services.doi_client import CrossrefDoiClient


def _reload_app() -> None:
    """Re-run AppConfig.ready() to apply settings change."""
    from django.apps import apps
    config = apps.get_app_config("fundingrequests")
    config.ready()


@pytest.mark.django_db
def test_demo_mode_wires_in_memory_client() -> None:
    with override_settings(CODA_DEMO_MODE=True):
        _reload_app()
        assert isinstance(DOIImportInputView.doi_client, InMemoryDOIMetadataClient)
        assert isinstance(DOIPreviewDetailView.doi_client, InMemoryDOIMetadataClient)
        assert isinstance(DOIPreviewSaveView.doi_client, InMemoryDOIMetadataClient)


@pytest.mark.django_db
def test_non_demo_mode_does_not_swap_client() -> None:
    with override_settings(CODA_DEMO_MODE=False):
        _reload_app()
        assert isinstance(DOIImportInputView.doi_client, CrossrefDoiClient)
        assert isinstance(DOIPreviewDetailView.doi_client, CrossrefDoiClient)
        assert isinstance(DOIPreviewSaveView.doi_client, CrossrefDoiClient)
```

### Step 2: Run tests to verify they fail

```bash
pdm run unittests tests/fundingrequests/test_demo_mode.py -v
```

Expected: both tests fail — `ready()` does not yet swap the client.

### Step 3: Implement `ready()` in `FundingrequestsConfig`

Replace `src/coda/apps/fundingrequests/apps.py`:

```python
from django.apps import AppConfig


class FundingrequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coda.apps.fundingrequests"

    def ready(self) -> None:
        from django.conf import settings

        if getattr(settings, "CODA_DEMO_MODE", False):
            from pathlib import Path

            from coda.apps.fundingrequests.views.doi_preview import (
                DOIImportInputView,
                DOIPreviewDetailView,
                DOIPreviewSaveView,
            )
            from coda.contexts.publication.services.fakes import InMemoryDOIMetadataClient

            client = InMemoryDOIMetadataClient.from_json(
                Path(settings.BASE_DIR) / "config/demo/fixtures/demo_dois.json"
            )
            DOIImportInputView.doi_client = client
            DOIPreviewDetailView.doi_client = client
            DOIPreviewSaveView.doi_client = client
```

Note: all imports are inside `ready()` to avoid import-time side effects — this is the Django-recommended pattern.

### Step 4: Run tests to verify they pass

```bash
pdm run unittests tests/fundingrequests/test_demo_mode.py -v
```

Expected: both tests pass.

### Step 5: Run the full test suite

```bash
pdm run unittests -v
```

Expected: all existing tests still pass. The `autouse` fixture in `test_doi_import_preview.py` reassigns `doi_client` on each test, so it is not affected by `ready()` running at startup in test mode (where `CODA_DEMO_MODE=False` by default).

### Step 6: Commit

```bash
git add src/coda/apps/fundingrequests/apps.py \
        tests/fundingrequests/test_demo_mode.py
git commit -m "feat(doi-import): wire InMemoryDOIMetadataClient in demo mode via AppConfig.ready()"
```

---

## Task 5: Verify end-to-end with `CODA_DEMO_MODE=True`

**Goal:** Confirm the full flow works manually before declaring done.

### Step 1: Start the server in demo mode

```bash
CODA_DEMO_MODE=True python manage.py runserver
```

### Step 2: Verify startup succeeds

Expected: no errors during startup. Server starts cleanly. If `demo_dois.json` fails Pydantic validation, you will see an exception at startup — fix the JSON.

### Step 3: Smoke test known DOI

Navigate to the DOI import page and submit `10.1038/s41586-020-2649-2`. Expected: preview page with "Array programming with NumPy".

### Step 4: Smoke test unknown DOI

Submit `10.9999/not-a-real-doi`. Expected: error message "This DOI is not available in the demo dataset".

### Step 5: Final commit (if any fixes needed)

```bash
git add <any fixed files>
git commit -m "fix(doi-import): <description of fix>"
```

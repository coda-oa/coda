# Import Scenarios Refinement

## Summary

Replace `PreviewArticleScenario` with two builder-style scenario classes (`ArticleScenario`, `BookScenario`) that auto-derive expected `FundingRequest` from their configuration. `FakeScenario` remains unchanged.

## Motivation

`PreviewArticleScenario` is essentially a `FakeScenario` with hardcoded values, a working `setup_db()`, and auto-derived expected FR. Making these capabilities available to all scenario classes reduces duplication and lets tests fine-tune individual properties without writing new fixture helpers.

## Design

### Three classes

| Class | `setup_db()` | `get_expected_fundingrequest()` | Purpose |
|-------|-------------|-------------------------------|---------|
| `FakeScenario` | no-op | raises unless manually configured | Client-only edge cases (print-ISSN, errors, coexistence) |
| `ArticleScenario` | creates publisher + journal | auto-derives `FundingRequest[Publication]` | Article import tests |
| `BookScenario` | creates publisher | auto-derives `FundingRequest[Monograph]` | Book import tests |

### `ArticleScenario` API

```python
ArticleScenario(fake_doi_client, doi="10.1234/preview.test")
    .with_title("Custom Title")          # default: "Test DOI Preview Article"
    .with_journal(title="Nature", eissn="1476-4687", publisher="Test Publisher", issn=None)
    .with_online_date(date(2024, 1, 1))  # set a specific online date
    .without_online_date()               # clear online date (None)
    .with_error()
```

Publisher is an attribute of the journal (the journal's publisher), not a standalone property for articles. When `eissn` is `None` (print-ISSN-only), `setup_db()` skips journal creation. All properties have sensible defaults matching the current `PreviewArticleScenario` behavior.

### `BookScenario` API

```python
BookScenario(fake_doi_client, doi="10.1234/book.test")
    .with_title("Custom Book")           # default: "Test Book"
    .with_publisher("Springer")          # default: "Springer International Publishing"
    .with_isbn("978-3-16-148410-0")      # default: "978-3-16-148410-0"
    .with_error()
```

### Behavior

- `setup_db()` creates the publisher (and journal for articles) using the configured values, then calls the appropriate metadata builder (`article_metadata()` / `book_metadata()`) and configures the DOI client
- `get_expected_fundingrequest()` auto-derives the expected `FundingRequest` from the configured values and the DB IDs created during `setup_db()`
- `with_error()` configures the client with a network error; calling `get_expected_fundingrequest()` after an error raises `RuntimeError`

### Changes to test file

- `expected_fundingrequest` fixture: `PreviewArticleScenario(fake_doi_client)` → `ArticleScenario(fake_doi_client)`
- No other tests change — all 8 existing `FakeScenario` usages remain

### Files modified

- `tests/contexts/publication/fixtures/sample_metadata.py` — add `ArticleScenario`, `BookScenario`; delete `PreviewArticleScenario`
- `tests/contexts/publication/fixtures/__init__.py` — update re-exports
- `tests/fundingrequests/test_doi_import_preview.py` — update import and fixture

### Non-goals

- `FakeScenario` behavior is not altered
- No changes to `NatureArticleScenario` or `SpringerBookScenario`
- No changes to the test logic of individual tests

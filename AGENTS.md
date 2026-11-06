Django app for managing open-access publication funding requests (submission → review → invoicing → reporting).

## Layout

- `src/coda/` — Python package (`coda.*`), on the path via uv.
  - `apps/` — Django layer (models, views, urls, forms, repositories).
    **Templates for ALL apps live centrally in `src/coda/apps/templates/<app>/`**, not inside app dirs.
  - `domain/` — pure domain model: frozen dataclasses, value objects; update via `dataclasses.replace`; **no Django imports**.
  - `contexts/` — application services + pydantic DTOs.
- `config/` — settings modules (`base`, `local`, `test`, `production`).
- `tests/` — mirrors the package; shared factories in `tests/modelfactory.py` (Django rows) / `tests/domainfactory.py` (domain objects).

## Architecture rules

- View → query service / persistence strategy → DTO → service (`contexts/`) → repository (`apps/`) → DB. Never bypass the service layer from views.
- DTOs subclass `CodaBaseDto` (`src/coda/apps/dto.py`); `to_post_data()` serializes them for wizard POSTs and maps `None` → `""`.
  "Absent means unchanged" fields are `str | None`; services skip `None` instead of overwriting.
- Multi-step forms use the in-house wizard framework (`coda.apps.wizard`: `Wizard` + `FormStep` + session `Store`; `complete()` builds DTOs → persistence strategy).
  Step templates are often shared between creation and update wizards and gated by context flags (e.g. `show_reviewer_remarks`, `page_title|default`) — always check both flows.

## Running things

Local dev stack (Django on :8000 + Postgres): `commands/start-coda.sh -l` / `stop-coda.sh -l`.
The host `.venv` has no configured database — run tests/lint/management **in the django container via uv** (repo mounted at `/app`):

```bash
docker exec -w /app coda_local_django uv run pytest tests/fundingrequests -q
docker exec -w /app coda_local_django sh -lc 'uv run ruff format <files> && uv run ruff check <files>'
```

Test selection via poe tasks (defined in `pyproject.toml`, run as `uv run poe <task>`) — DB suites run parallel via `pytest-xdist` — new tests must be parallel-safe (no fixed ports, no shared module state, no execution-order deps). Tests use `--reuse-db` (in `addopts`), so pass `--create-db` after schema/migration changes. `tests/database/conftest.py` gives migration tests their own databases because `django_test_migrations` mutates schema mid-run.
- `uv run poe unittests` — everything not marked integration/migration/performance
- `uv run poe integrationtests`
- `uv run poe migrationtests`
- `uv run poe uitests`
- `uv run poe alltests`, `uv run poe coverage`
Pre-commit runs ruff, djlint (templates), mypy `--strict` (+django/pydantic stubs), commitizen.

## Tests

- pytest-django; DB-backed tests need `@pytest.mark.django_db`. Assert observable behavior (repo state, rendered HTML), not internals.
- Wizard flows: databuilders + `WizardSubmitter.submit_all()` in `tests/fundingrequests/wizard/`, parametrized with `@UseWizardSubmitter.singular/distinct`.

## Conventions

- Commits: Conventional Commits, lowercase scoped — `feat(fundingrequests): ...`.

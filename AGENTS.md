Django app for managing open-access publication funding requests (submission → review → invoicing → reporting).

## Layout

- `src/coda/` — Python package (`coda.*`), on the path via pdm.
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
The host `.venv` has no configured database — run tests/lint/management **in the django container via pdm** (repo mounted at `/app`):

```bash
docker exec -w /app coda_local_django pdm run pytest tests/fundingrequests -q
docker exec -w /app coda_local_django sh -lc 'pdm run ruff format <files> && pdm run ruff check <files>'
```

Test selection via pdm scripts: `unittests`, `integrationtests`, `migrationtests`, `uitests`.
Pre-commit runs ruff, djlint (templates), mypy `--strict` (+django/pydantic stubs), commitizen.

## Tests

- pytest-django; DB-backed tests need `@pytest.mark.django_db`. Assert observable behavior (repo state, rendered HTML), not internals.
- Wizard flows: databuilders + `WizardSubmitter.submit_all()` in `tests/fundingrequests/wizard/`, parametrized with `@UseWizardSubmitter.singular/distinct`.

## Conventions

- Commits: Conventional Commits, lowercase scoped — `feat(fundingrequests): ...`.

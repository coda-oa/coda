"""
Migration tests (django_test_migrations) replay migrations to intermediate
states on the default test database. That would corrupt the schema that
`--reuse-db` keeps between runs of the regular test suites, so these tests
run against their own test database.

Must depend on `django_db_modify_db_settings_parallel_suffix` so xdist
workers still get per-worker suffixed database names.
"""

import pytest
from django.conf import settings


def _worker_runs_only_migration_tests(request: pytest.FixtureRequest) -> bool:
    items = request.session.items
    return bool(items) and all(item.get_closest_marker("migration_test") for item in items)


@pytest.fixture(scope="session")
def django_db_modify_db_settings(
    request: pytest.FixtureRequest,
    django_db_modify_db_settings_parallel_suffix: None,
) -> None:
    if not _worker_runs_only_migration_tests(request):
        return
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "")
    for db_settings in settings.DATABASES.values():
        db_settings["TEST"]["NAME"] = f"test_coda_migrations{worker_id}"

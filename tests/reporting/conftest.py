"""Shared fixtures for the reporting tests.

The statistics fact cache is per-process and lives across tests: a cached
fact set from one test would answer the next test's identical GET, making
results order-dependent. Every test starts and ends with an empty cache."""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_fact_cache() -> None:
    cache.clear()
    yield
    cache.clear()

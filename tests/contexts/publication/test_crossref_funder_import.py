"""Tests for DOI import with funders (using fake clients).

Verifies that funders referenced in Crossref metadata are correctly
resolved and imported into FundingRequests — without hitting live APIs.
"""

import pytest
from tests.contexts.publication.fixtures import FundedArticleScenario
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

from coda.apps.fundingrequests import repository
from coda.contexts.publication.services.doi_client import crossref
from coda.contexts.publication.services.doi_import_service import DOIImportService


@pytest.fixture(params=["fake", "real"])
def scenario(request: pytest.FixtureRequest) -> FundedArticleScenario:
    if request.param == "fake":
        scenario = FundedArticleScenario.with_in_memory_client()
    else:
        scenario = FundedArticleScenario(crossref)

    scenario.setup_db()
    return scenario


# FIXME: test fails for the "real" Crossref client because `override_funding()` in
# `external_metadata.py` strips funder identifiers (DOIs) when called from
# `OverrideImport.apply()` in `doi_import_service.py`. Even with an empty
# override, `apply()` calls ``metadata.override_funding()` with only
# `(name, project_id)` tuples, losing the funder DOIs. This means
# `_resolve_funders()` can't call `fetch_funder()` to resolve canonical names,
# so the real API's "Bundesministerium für Bildung und Forschung" never gets
# resolved to "Bundesministerium für Forschung, Technologie und Raumfahrt",
# creating a new funder instead of matching the existing one.
# Fix: preserve identifiers in `override_funding()` and pass them through
# `apply()`.


@pytest.mark.django_db
def test__doi_with_funders__imports_funders_into_fundingrequest(
    scenario: FundedArticleScenario,
) -> None:
    sut = DOIImportService(scenario.client)

    fr_id = sut.import_from_doi(scenario.doi)

    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())

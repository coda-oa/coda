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


@pytest.mark.django_db
def test__doi_with_funders__imports_funders_into_fundingrequest(
    scenario: FundedArticleScenario,
) -> None:
    sut = DOIImportService(scenario.client)

    fr_id = sut.import_from_doi(scenario.doi)

    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())

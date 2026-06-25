"""Tests for DOI import with funders (using fake clients).

Verifies that funders referenced in Crossref metadata are correctly
resolved and imported into FundingRequests — without hitting live APIs.
"""

import pytest
from tests.contexts.publication.fixtures import FundedArticleScenario
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

from coda.apps.fundingrequests import repository
from coda.contexts.publication.services.doi_import_service import DOIImportService


@pytest.mark.django_db
def test__doi_with_funders__imports_funders_into_fundingrequest() -> None:
    scenario = FundedArticleScenario.with_in_memory_client()
    scenario.setup_db()
    sut = DOIImportService(scenario.client)

    fr_id = sut.import_from_doi(scenario.doi)

    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())

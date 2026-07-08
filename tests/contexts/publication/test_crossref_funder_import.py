"""Tests for DOI import with funders (using fake clients).

Verifies that funders referenced in Crossref metadata are correctly
resolved and imported into FundingRequests — without hitting live APIs.

Funder resolution uses the ROR batch API or falls back to Crossref metadata
names; the old doi.org content negotiation path has been removed.
"""

from typing import Any

import httpx
import pytest
from tests.contexts.publication.fixtures import FundedArticleScenario
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

from coda.apps.fundingrequests import repository
from coda.contexts.publication.services.doi_client._ror import RORClient
from coda.contexts.publication.services.doi_import_service import DOIImportService

EMPTY_ROR_RESPONSE: dict[str, object] = {"number_of_results": 0, "items": []}


class FakeRORHttpGet:
    """Returns an empty ROR API response — no funders resolved via ROR."""

    def __init__(self, status: int = 200, json_data: dict[str, Any] | None = None) -> None:
        self._json_data = json_data or EMPTY_ROR_RESPONSE
        self._status = status

    def get(self, url: str, **kwargs: Any) -> Any:
        response = httpx.Response(
            self._status,
            json=self._json_data,
            request=httpx.Request("GET", url),
        )
        if self._status >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP error {self._status}",
                request=httpx.Request("GET", url),
                response=response,
            )
        return response


@pytest.mark.django_db
def test__doi_with_funders__imports_funders_into_fundingrequest() -> None:
    scenario = FundedArticleScenario.with_in_memory_client()
    scenario.setup_db()

    ror_client = RORClient(http_client=FakeRORHttpGet())
    sut = DOIImportService(scenario.client, ror_client=ror_client)

    fr_id = sut.import_from_doi(scenario.doi)

    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())

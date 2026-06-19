from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from coda.contexts.publication.dto.external_metadata import (
    ExternalFundingOrganisationMetadata,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client.errors import DOIFetchError, DOINotFoundError
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
        self._funders: dict[str, ExternalFundingOrganisationMetadata] = {}
        self._errors: dict[str, ErrorType] = {}

    @classmethod
    def from_json(cls, path: Path) -> InMemoryDOIMetadataClient:
        """Load and validate a JSON fixture file.

        JSON format: { "<doi>": <ExternalPublicationMetadata as JSON>, ... }

        Raises:
            json.JSONDecodeError: if file content is not valid JSON
            pydantic.ValidationError: if any entry fails ExternalPublicationMetadata validation
        """
        client = cls()
        raw: dict[str, object] = json.loads(path.read_text())
        client.data = {
            doi: ExternalPublicationMetadata.model_validate(meta) for doi, meta in raw.items()
        }
        return client

    def configure_funder(self, doi: Doi, funder: ExternalFundingOrganisationMetadata) -> None:
        """Configure a funder DOI to return specific metadata when fetched.

        Useful in tests to simulate funder resolution without hitting Crossref.
        """
        self._funders[str(doi)] = funder

    def configure_error(self, doi: Doi, error_type: ErrorType) -> None:
        """Configure a DOI to raise a specific error when fetched.

        Useful in tests to simulate network/API failure scenarios.
        """
        self._errors[str(doi)] = error_type

    def fetch_publication(self, doi: Doi) -> ExternalPublicationMetadata:
        doi_str = str(doi)
        if doi_str in self._errors:
            error_type = self._errors[doi_str]
            raise DOIFetchError(doi, _ERROR_MESSAGES[error_type])
        if doi_str not in self.data:
            raise DOINotFoundError(doi, "This DOI is not available in the demo dataset")
        return self.data[doi_str]

    def fetch_funder(self, doi: Doi) -> ExternalFundingOrganisationMetadata:
        doi_str = str(doi)
        if doi_str in self._errors:
            error_type = self._errors[doi_str]
            raise DOIFetchError(doi, _ERROR_MESSAGES[error_type])
        if doi_str not in self._funders:
            raise DOINotFoundError(doi, "This funder DOI is not available in the demo dataset")
        return self._funders[doi_str]

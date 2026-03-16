"""Test doubles for DOI metadata clients.

This module contains fake/stub implementations for testing purposes only.
The fake client starts empty - tests should configure it with test data.
"""

from typing import Literal

from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services.doi_client import DOIFetchError, DOINotFoundError
from coda.domain.publication.links import Doi

ErrorType = Literal["timeout", "network", "server_error", "rate_limit"]

_ERROR_MESSAGES: dict[ErrorType, str] = {
    "timeout": "Request timeout",
    "network": "Network connection failed",
    "server_error": "Server returned 500 error",
    "rate_limit": "Rate limit exceeded (429)",
}


class FakeDOIMetadataClient:
    """Fake DOI metadata client for testing.

    This client starts with no data. Tests should configure it with metadata
    using the `data` attribute or by calling helper methods.

    Example:
        >>> from tests.contexts.publication.fixtures.test_metadata import nature_article_metadata
        >>> client = FakeDOIMetadataClient()
        >>> client.data["10.1038/nature12373"] = nature_article_metadata()
    """

    def __init__(self) -> None:
        # Empty by default - tests configure with specific data
        self.data: dict[str, ExternalPublicationMetadata] = {}
        self._errors: dict[str, ErrorType] = {}

    def configure_error(self, doi: Doi, error_type: ErrorType) -> None:
        """Configure the client to raise an error for a specific DOI.

        Args:
            doi: The DOI that should trigger an error
            error_type: Type of error to raise ('timeout', 'network', 'server_error', 'rate_limit')
        """
        self._errors[str(doi)] = error_type

    def fetch(self, doi: Doi) -> ExternalPublicationMetadata:
        """Fetch metadata from hardcoded test data or raise configured error."""
        doi_str = str(doi)

        if doi_str in self._errors:
            error_type = self._errors[doi_str]
            raise DOIFetchError(doi, _ERROR_MESSAGES[error_type])

        if doi_str not in self.data:
            raise DOINotFoundError(doi)

        return self.data[doi_str]

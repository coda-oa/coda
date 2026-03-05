"""Test doubles for DOI metadata clients.

This module contains fake/stub implementations for testing purposes only.
The fake client starts empty - tests should configure it with test data.
"""

from coda.contexts.publication.dto.external_metadata import ExternalPublicationMetadata
from coda.contexts.publication.services.doi_client import DOIFetchError, DOINotFoundError
from coda.domain.publication.links import Doi


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
        self._errors: dict[str, str] = {}

    def configure_error(self, doi: Doi, error_type: str) -> None:
        """Configure the client to raise an error for a specific DOI.

        Args:
            doi: The DOI that should trigger an error
            error_type: Type of error to raise ('timeout', 'network', 'server_error', 'rate_limit')
        """
        self._errors[str(doi)] = error_type

    def fetch(self, doi: Doi) -> ExternalPublicationMetadata:
        """Fetch metadata from hardcoded test data or raise configured error."""
        doi_str = str(doi)

        # Check if this DOI is configured to raise an error
        if doi_str in self._errors:
            error_type = self._errors[doi_str]
            if error_type == "timeout":
                raise DOIFetchError(doi, "Request timeout")
            elif error_type == "network":
                raise DOIFetchError(doi, "Network connection failed")
            elif error_type == "server_error":
                raise DOIFetchError(doi, "Server returned 500 error")
            elif error_type == "rate_limit":
                raise DOIFetchError(doi, "Rate limit exceeded (429)")
            else:
                raise DOIFetchError(doi, f"Unknown error type: {error_type}")

        # Normal behavior
        if doi_str not in self.data:
            raise DOINotFoundError(doi)

        return self.data[doi_str]

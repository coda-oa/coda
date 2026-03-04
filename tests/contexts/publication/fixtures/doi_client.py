"""Test doubles for DOI metadata clients.

This module contains fake/stub implementations for testing purposes only.
"""

import datetime

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client import DOIFetchError, DOINotFoundError
from coda.domain.publication.links import Doi


class FakeDOIMetadataClient:
    """Fake DOI metadata client for testing.

    Provides hardcoded responses for known test DOIs and can be configured
    to simulate error scenarios.
    """

    def __init__(self) -> None:
        # Hardcoded test data for known DOIs
        # Public attribute to allow tests to add custom test data
        self.data = {
            "10.1038/nature12373": ExternalPublicationMetadata(
                title="Example Nature Article",
                authors=[
                    ExternalAuthor(
                        name="John Doe",
                        affiliation="University of Example",
                        ror_id="https://ror.org/01an7q238",
                    ),
                    ExternalAuthor(
                        name="Jane Smith",
                        affiliation="Research Institute",
                        ror_id=None,
                    ),
                ],
                publication_type="journal-article",
                journal=ExternalJournal(
                    title="Nature",
                    issn="0028-0836",
                    eissn="1476-4687",
                ),
                publisher="Springer Science and Business Media LLC",
                license="CC-BY",
                online_publication_date=datetime.date(2024, 1, 15),
            ),
        }
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

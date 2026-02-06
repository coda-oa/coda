"""DOI metadata client - protocol and implementations.

This module provides the anti-corruption layer for fetching publication metadata
from external sources (Crossref, DataCite).
"""

import datetime
from typing import Any, Protocol

import httpx

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.domain.errors import DomainError
from coda.domain.publication.links import Doi


class DOINotFoundError(DomainError):
    """Raised when a DOI is not found in external metadata sources."""

    def __init__(self, doi: Doi, *args: object) -> None:
        super().__init__(f"DOI not found: {doi}", *args)
        self.doi = doi


class DOIFetchError(DomainError):
    """Raised when DOI fetch fails due to network/API errors.

    This is distinct from DOINotFoundError (404) - this represents
    infrastructure failures like timeouts, network errors, server errors.
    """

    def __init__(self, doi: Doi, reason: str, *args: object) -> None:
        super().__init__(f"Failed to fetch DOI {doi}: {reason}", *args)
        self.doi = doi
        self.reason = reason


class DOIMetadataClient(Protocol):
    """Protocol for fetching publication metadata by DOI.

    This defines the contract that both fake and real implementations must follow.
    """

    def fetch(self, doi: Doi) -> ExternalPublicationMetadata:
        """Fetch publication metadata for a given DOI.

        Args:
            doi: The DOI to fetch metadata for

        Returns:
            ExternalPublicationMetadata with publication details

        Raises:
            DOINotFoundError: If the DOI is not found (404)
            DOIFetchError: If the fetch fails due to network/API errors
        """
        ...


class CrossrefDoiClient:
    """Real DOI metadata client using Crossref REST API.

    Fetches metadata from Crossref (and DataCite fallback in future).
    """

    CROSSREF_API_BASE = "https://api.crossref.org/works/"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def fetch(self, doi: Doi) -> ExternalPublicationMetadata:
        """Fetch metadata from Crossref API.

        Raises:
            DOINotFoundError: If DOI not found (404)
            DOIFetchError: If request fails due to network/API errors
        """
        url = f"{self.CROSSREF_API_BASE}{doi}"

        try:
            response = httpx.get(url, timeout=self.timeout, follow_redirects=True)

            if response.status_code == 404:
                raise DOINotFoundError(doi)

            response.raise_for_status()
            data = response.json()

            return self._parse_crossref_response(data)

        except DOINotFoundError:
            # Re-raise domain exceptions without wrapping
            raise

        except DOIFetchError:
            # Re-raise domain exceptions without wrapping
            raise

        except httpx.TimeoutException as e:
            raise DOIFetchError(doi, "Request timeout") from e

        except httpx.ConnectError as e:
            raise DOIFetchError(doi, "Network connection failed") from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise DOINotFoundError(doi) from e
            # Translate HTTP errors to domain exception
            status = e.response.status_code
            if status == 429:
                raise DOIFetchError(doi, "Rate limit exceeded (429)") from e
            elif 500 <= status < 600:
                raise DOIFetchError(doi, f"Server error ({status})") from e
            else:
                raise DOIFetchError(doi, f"HTTP error ({status})") from e

        except ValueError as e:
            # JSON decode errors
            raise DOIFetchError(doi, "Invalid JSON response from API") from e

        except httpx.HTTPError as e:
            # Catch-all for any other httpx errors (network issues, etc.)
            raise DOIFetchError(doi, f"Network error: {type(e).__name__}") from e

    def _parse_crossref_response(self, data: dict[str, Any]) -> ExternalPublicationMetadata:
        """Parse Crossref JSON response into our metadata structure."""
        message = data.get("message", {})

        titles = message.get("title", [])
        title = titles[0] if titles else "Untitled"
        authors = self._parse_authors(message.get("author", []))
        pub_type = message.get("type", "unknown")
        journal = self._parse_journal(message) if pub_type == "journal-article" else None
        publisher = message.get("publisher")

        license_info = self._parse_license(message.get("license", []))

        # Parse both online and print publication dates
        online_date = self._parse_date(message.get("published-online"))
        print_date = self._parse_date(message.get("published-print"))

        return ExternalPublicationMetadata(
            title=title,
            authors=authors,
            publication_type=pub_type,
            journal=journal,
            publisher=publisher,
            license=license_info,
            online_publication_date=online_date,
            print_publication_date=print_date,
        )

    def _parse_authors(self, author_data: list[dict[str, Any]]) -> list[ExternalAuthor]:
        """Parse author list from Crossref format."""
        authors = []

        for author in author_data:
            # Crossref format: {"given": "John", "family": "Doe", "affiliation": [...]}
            given = author.get("given", "")
            family = author.get("family", "")
            name = f"{given} {family}".strip() if given or family else "Unknown Author"

            # Extract first affiliation and ROR if available
            affiliations = author.get("affiliation", [])
            affiliation_name = None
            ror_id = None

            if affiliations:
                first_affil = affiliations[0]
                affiliation_name = first_affil.get("name")

                # Check for ROR ID in affiliation
                affil_ids = first_affil.get("id", [])
                for aid in affil_ids:
                    if aid.get("id-type") == "ROR":
                        ror_id = aid.get("id")
                        break

            authors.append(
                ExternalAuthor(
                    name=name,
                    affiliation=affiliation_name,
                    ror_id=ror_id,
                )
            )

        return authors

    def _parse_journal(self, message: dict[str, Any]) -> ExternalJournal | None:
        """Parse journal information from Crossref response."""
        # Journal title is in "container-title" field
        container_titles = message.get("container-title", [])
        if not container_titles:
            return None

        title = container_titles[0]

        # Extract ISSNs
        issns = message.get("ISSN", [])
        issn_types = message.get("issn-type", [])

        issn = None
        eissn = None

        # Match ISSNs with their types
        for issn_data in issn_types:
            issn_value = issn_data.get("value")
            issn_type = issn_data.get("type")

            if issn_type == "print":
                issn = issn_value
            elif issn_type == "electronic":
                eissn = issn_value

        # Fallback: if no type info, just take first two ISSNs
        if not issn and not eissn and issns:
            issn = issns[0] if len(issns) > 0 else None
            eissn = issns[1] if len(issns) > 1 else None

        return ExternalJournal(title=title, issn=issn, eissn=eissn)

    def _parse_license(self, license_data: list[dict[str, Any]]) -> str | None:
        """Parse license information from Crossref response."""
        if not license_data:
            return None

        # Take the first license URL
        first_license = license_data[0]
        url = first_license.get("URL", "")

        # Extract license type from URL (e.g., "CC-BY" from creative commons URL)
        if "creativecommons.org/licenses/" in url:
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                license_type = parts[-2].upper()
                return f"CC-{license_type}" if not license_type.startswith("CC") else license_type

        return url if url else None

    def _parse_date(self, date_data: dict[str, Any] | None) -> datetime.date | None:
        """Parse date from Crossref format.

        Crossref returns: {"date-parts": [[2024, 1, 15]]}
        """
        if not date_data:
            return None

        date_parts = date_data.get("date-parts", [[]])[0]

        if not date_parts:
            return None

        # Date parts: [year, month, day] (month and day optional)
        year = date_parts[0] if len(date_parts) > 0 else None
        month = date_parts[1] if len(date_parts) > 1 else 1
        day = date_parts[2] if len(date_parts) > 2 else 1

        if not year:
            return None

        try:
            return datetime.date(year, month, day)
        except ValueError:
            # Invalid date (e.g., Feb 30), just return year-01-01
            return datetime.date(year, 1, 1)

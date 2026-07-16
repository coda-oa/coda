"""DOI metadata client - protocol and implementations.

This module provides the anti-corruption layer for fetching publication metadata
from external sources (Crossref, DataCite).
"""

from typing import Protocol


from coda.contexts.fundingrequest.dto.external_metadata import (
    ExternalPublicationMetadata,
)
from coda.domain.publication.links import Doi


class DOIMetadataClient(Protocol):
    """Protocol for fetching publication metadata by DOI.

    This defines the contract that both fake and real implementations must follow.

    Funder resolution (ROR enrichment + DB match/persist) is handled by
    ``resolve_funders`` in the fundingrequest context's ``funder_resolver``
    module.
    """

    def fetch_publication(self, doi: Doi) -> ExternalPublicationMetadata:
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

    def fetch_publications_batch(
        self, dois: list[Doi]
    ) -> dict[str, ExternalPublicationMetadata | Exception]:
        """Fetch metadata for multiple DOIs in a single batch call.

        Args:
            dois: List of DOIs to fetch metadata for

        Returns:
            Dict keyed by DOI string. Each value is either the parsed
            ExternalPublicationMetadata or an Exception (DOINotFoundError, DOIFetchError).
        """
        ...

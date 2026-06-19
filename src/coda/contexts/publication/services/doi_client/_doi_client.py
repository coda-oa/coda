"""DOI metadata client - protocol and implementations.

This module provides the anti-corruption layer for fetching publication metadata
from external sources (Crossref, DataCite).
"""

from typing import Protocol


from coda.contexts.publication.dto.external_metadata import (
    ExternalFundingOrganisationMetadata,
    ExternalPublicationMetadata,
)
from coda.domain.publication.links import Doi


class DOIMetadataClient(Protocol):
    """Protocol for fetching publication metadata by DOI.

    This defines the contract that both fake and real implementations must follow.
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

    def fetch_funder(self, doi: Doi) -> ExternalFundingOrganisationMetadata:
        """Fetch canonical funder metadata for a funder DOI.

        Args:
            doi: The funder's DOI (e.g. 10.13039/...)

        Returns:
            ExternalFundingOrganisationMetadata with canonical name

        Raises:
            DOINotFoundError: If the funder DOI is not found (404)
            DOIFetchError: If the fetch fails due to network/API errors
        """
        ...

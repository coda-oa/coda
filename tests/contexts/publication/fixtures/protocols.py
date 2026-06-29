from typing import Protocol, Self, TypeVar
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.contexts.publication.services.doi_client._doi_client import DOIMetadataClient
from coda.domain.publication.links import Doi

TFundingRequest = TypeVar("TFundingRequest", bound=AnyFundingRequest, covariant=True)


class ImportScenario(Protocol):
    """Protocol defining the interface for DOI import test scenarios."""

    @property
    def doi(self) -> Doi:
        """The DOI string used in this scenario."""
        ...

    @property
    def client(self) -> DOIMetadataClient:
        """The DOI client associated with this scenario."""
        ...

    def setup_db(self) -> Self:
        """Create DB prerequisites (publishers, journals, funders)."""
        ...

    def get_expected_fundingrequest(self) -> AnyFundingRequest:
        """Return the exact FundingRequest domain object expected after import."""
        ...

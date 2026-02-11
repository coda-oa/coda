from typing import Protocol

from coda.apps.publications.dto import ContractYearDto, PublicationBaseDto
from coda.contexts.fundingrequest.dto.commands import (
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
    UpdatePublicationMetadataCommand,
)
from coda.domain.contract import PublisherId
from coda.domain.publication import JournalId


class FundingRequestPersistenceStrategy(Protocol):
    """Strategy for loading and persisting funding request data.

    This protocol defines a clean interface between wizards and persistence.
    The strategy works only with DTOs - it has no knowledge of:
    - Store structure (wizard's responsibility)
    - Article vs monograph distinctions (wizard's responsibility)
    - UI workflow logic (wizard's responsibility)

    The wizard extracts data from its Store, converts to DTOs, and passes
    to the strategy for persistence.
    """

    def load_publication(self) -> PublicationBaseDto:
        """Load publication data (article or monograph) as base DTO."""
        ...

    def save_publication_metadata(self, metadata: UpdatePublicationMetadataCommand) -> None:
        """Persist publication metadata only."""
        ...

    def save_journal_and_contracts(
        self, journal: JournalId, contracts: list[ContractYearDto]
    ) -> None:
        """Persist journal and contracts for article publication."""
        ...

    def save_publisher_and_contracts(
        self, publisher: PublisherId, contracts: list[ContractYearDto]
    ) -> None:
        """Persist publisher and contracts for monograph publication."""
        ...

    def load_funding(self) -> tuple[PaymentDto, list[ExternalFundingDto]]:
        """Load funding data as DTOs (cost, external funding)."""
        ...

    def save_funding(self, cost: PaymentDto, funding: list[ExternalFundingDto]) -> None:
        """Persist funding data."""
        ...

    def load_extra_information(self) -> ExtraInformationDto:
        """Load extra information as DTO."""
        ...

    def save_extra_information(self, extra_info: ExtraInformationDto) -> None:
        """Persist extra information."""
        ...

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.publications.dto import (
    ContractYearDto,
    MonographDto,
    PublicationBaseDto,
    PublicationDto,
)
from coda.apps.publications.repositories import publication_repository
from coda.contexts.fundingrequest.dto.commands import (
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
    UpdatePublicationMetadataCommand,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.publication import JournalId
from coda.domain.publication.publication import Monograph, Publication


class DatabasePersistenceStrategy:
    """Persistence strategy that loads from and saves to the database.

    This strategy encapsulates all database access for funding request wizards.
    It works only with DTOs and has no knowledge of:
    - Store structure (wizard's responsibility)
    - Article vs monograph distinctions (uses polymorphic load, specialized saves)
    - UI workflow logic (wizard's responsibility)
    """

    def __init__(self, funding_request_id: int):
        """Initialize strategy with funding request ID.

        Args:
            funding_request_id: ID of the funding request to load/save
        """
        self.funding_request_id = FundingRequestId(funding_request_id)

    def load_publication(self) -> PublicationBaseDto:
        """Load publication data (article or monograph) as base DTO.

        The repository returns the appropriate type (Article or Monograph),
        and the corresponding DTO is created via from_publication/from_monograph.
        """

        publication = publication_repository.get_by_fundingrequest_id(self.funding_request_id)
        if isinstance(publication, Publication):
            return PublicationDto.from_publication(publication)
        elif isinstance(publication, Monograph):
            return MonographDto.from_monograph(publication)

        raise ValueError("Invalid FundingRequest")

    def save_publication_metadata(self, metadata: UpdatePublicationMetadataCommand) -> None:
        """Persist publication metadata only."""
        fundingrequests.update_publication_metadata(self.funding_request_id, metadata)

    def save_journal_and_contracts(
        self, journal: JournalId, contracts: list[ContractYearDto]
    ) -> None:
        """Persist journal and contracts for article publication."""
        fundingrequests.update_publication_journal_and_contracts(
            self.funding_request_id, journal, contracts
        )

    def save_publisher_and_contracts(
        self, publisher: PublisherId, contracts: list[ContractYearDto]
    ) -> None:
        """Persist publisher and contracts for monograph publication."""
        fundingrequests.update_publication_publisher_and_contracts(
            self.funding_request_id, publisher, contracts
        )

    def load_funding(self) -> tuple[PaymentDto, list[ExternalFundingDto]]:
        """Load funding data as DTOs."""
        fr = fundingrequest_repository.get_by_id(self.funding_request_id)
        cost = PaymentDto.from_payment(fr.estimated_cost)
        funding = [ExternalFundingDto.from_external_funding(ef) for ef in fr.external_funding]
        return cost, funding

    def save_funding(self, cost: PaymentDto, funding: list[ExternalFundingDto]) -> None:
        """Persist funding data."""
        fundingrequests.update_funding(self.funding_request_id, cost, funding)

    def load_extra_information(self) -> ExtraInformationDto:
        """Load extra information as DTO."""
        fr = fundingrequest_repository.get_by_id(self.funding_request_id)
        from coda.contexts.fundingrequest.dto.commands import ExtraContactDto

        contact = ExtraContactDto()
        if fr.extra_contact:
            contact = ExtraContactDto(name=fr.extra_contact.name, email=fr.extra_contact.email)

        return ExtraInformationDto(
            request_remarks=fr.request_remarks,
            extra_contact=contact,
            reviewer_remarks=fr.review_remarks,
        )

    def save_extra_information(self, extra_info: ExtraInformationDto) -> None:
        """Persist extra information."""
        fundingrequests.update_extra_information(self.funding_request_id, extra_info)

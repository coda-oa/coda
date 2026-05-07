import abc
import datetime
import uuid
from typing import Literal


from coda.apps.authors.dto import AuthorDto
from coda.apps.contracts import repository as contract_services
from coda.apps.dto import CodaBaseDto, OptionalFromStr
from coda.domain.author import AuthorNames
from coda.domain.contract import ContractId, ContractYear, GetContractById, PublisherId
from coda.domain.publication import (
    Authors,
    BasePublication,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
    links,
)
from coda.domain.publication.publication import JournalId
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import ConceptId, VocabularyConcept, VocabularyId


class LinkDto(CodaBaseDto):
    link_type: str
    link_value: str

    @classmethod
    def from_link(cls, link: Link) -> "LinkDto":
        return LinkDto(link_type=link.type(), link_value=link.value())

    def to_link(self) -> Link:
        return links.create_link(self.link_type, self.link_value)


class ConceptDto(CodaBaseDto):
    id: uuid.UUID
    concept: str
    vocabulary: VocabularyId
    name: str = ""
    description: str = ""

    @classmethod
    def from_concept(cls, concept: VocabularyConcept) -> "ConceptDto":
        return cls(
            id=concept.id,
            concept=concept.concept_id,
            vocabulary=concept.vocabulary,
            name=concept.name,
            description=concept.description,
        )

    def to_concept(self) -> VocabularyConcept:
        return VocabularyConcept(
            id=ConceptId(str(self.id)),
            concept_id=self.concept,
            vocabulary=VocabularyId(self.vocabulary),
            name=self.name,
            description=self.description,
        )


class PublicationMetaDto(CodaBaseDto):
    title: str
    publication_type: ConceptDto
    subject_area: ConceptDto
    open_access_type: str
    license: str
    publication_state: str
    online_publication_date: OptionalFromStr[datetime.date]
    print_publication_date: OptionalFromStr[datetime.date]


class JournalDto(CodaBaseDto):
    id: int


class ContractYearDto(CodaBaseDto):
    contract: int
    year: int

    @classmethod
    def from_contract_year(cls, contract_year: ContractYear) -> "ContractYearDto":
        return cls(contract=contract_year.contract.id.pk, year=contract_year.year)

    def to_contract_year(self, get_contract_by_id: GetContractById | None = None) -> ContractYear:
        """Convert DTO to domain ContractYear object.

        Args:
            get_contract_by_id: Optional callable to fetch Contract by ID.
                Defaults to contract_services.get_by_id if not provided.

        Returns:
            Domain ContractYear object
        """
        if get_contract_by_id is None:
            get_contract_by_id = contract_services.get_by_id

        contract = get_contract_by_id(ContractId(self.contract))
        return contract.in_year(self.year)


class PublicationBaseDto(abc.ABC, CodaBaseDto):
    publication_kind: str  # Discriminator field for Pydantic polymorphic deserialization
    meta: PublicationMetaDto
    contracts: list[ContractYearDto]
    links: list[LinkDto]
    relevant_authors: list[AuthorDto]
    other_authors: list[str]

    @abc.abstractmethod
    def to_publication(
        self, id: PublicationId | None = None, get_contract_by_id: GetContractById | None = None
    ) -> BasePublication: ...


class PublicationDto(PublicationBaseDto):
    publication_kind: Literal["journal_article"] = "journal_article"
    journal: JournalDto

    @classmethod
    def from_publication(cls, publication: Publication) -> "PublicationDto":
        match publication.publication_state:
            case Published(online_date, print_date):
                online_pub_date = online_date
                print_pub_date = print_date
            case _:
                online_pub_date = None
                print_pub_date = None

        return cls(
            meta=PublicationMetaDto(
                title=publication.title,
                license=publication.license.name,
                subject_area=ConceptDto.from_concept(publication.subject_area),
                publication_type=ConceptDto.from_concept(publication.publication_type),
                open_access_type=publication.open_access_type.name,
                publication_state=publication.publication_state.name(),
                online_publication_date=online_pub_date,
                print_publication_date=print_pub_date,
            ),
            journal=JournalDto(id=publication.journal.pk),
            contracts=[
                ContractYearDto(contract=c.contract.id.pk, year=c.year)
                for c in publication.contracts
            ],
            links=[LinkDto.from_link(link) for link in publication.links],
            relevant_authors=list(map(AuthorDto.from_author, publication.relevant_authors)),
            other_authors=list(publication.other_authors),
        )

    def to_publication(
        self, id: PublicationId | None = None, get_contract_by_id: GetContractById | None = None
    ) -> Publication:
        """Convert DTO to domain Publication object.

        Args:
            id: Optional publication ID
            get_contract_by_id: Optional callable to fetch Contract by ID.
                Passed through to ContractYearDto.to_contract_year()

        Returns:
            Domain Publication object
        """
        return Publication(
            id=id or PublicationId(),
            title=NonEmptyStr(self.meta.title),
            license=License.of(self.meta.license),
            publication_type=self.meta.publication_type.to_concept(),
            subject_area=self.meta.subject_area.to_concept(),
            open_access_type=OpenAccessType[self.meta.open_access_type],
            publication_state=parse_publication_state(self.meta),
            relevant_authors=Authors(a.to_author() for a in self.relevant_authors),
            other_authors=AuthorNames(self.other_authors),
            links={link.to_link() for link in self.links},
            contracts=tuple(c.to_contract_year(get_contract_by_id) for c in self.contracts),
            journal=JournalId(self.journal.id),
        )


class MonographDto(PublicationBaseDto):
    publication_kind: Literal["monograph"] = "monograph"
    publisher: PublisherId

    @classmethod
    def from_monograph(cls, publication: Monograph) -> "MonographDto":
        match publication.publication_state:
            case Published(online_date, print_date):
                online_pub_date = online_date
                print_pub_date = print_date
            case _:
                online_pub_date = None
                print_pub_date = None

        return cls(
            meta=PublicationMetaDto(
                title=publication.title,
                license=publication.license.name,
                subject_area=ConceptDto.from_concept(publication.subject_area),
                publication_type=ConceptDto.from_concept(publication.publication_type),
                open_access_type=publication.open_access_type.name,
                publication_state=publication.publication_state.name(),
                online_publication_date=online_pub_date,
                print_publication_date=print_pub_date,
            ),
            publisher=publication.publisher,
            contracts=list(ContractYearDto.from_contract_year(c) for c in publication.contracts),
            links=[LinkDto.from_link(link) for link in publication.links],
            relevant_authors=list(map(AuthorDto.from_author, publication.relevant_authors)),
            other_authors=list(publication.other_authors),
        )

    def to_monograph(
        self, id: PublicationId | None = None, get_contract_by_id: GetContractById | None = None
    ) -> Monograph:
        """Convert DTO to domain Monograph object.

        Args:
            id: Optional publication ID
            get_contract_by_id: Optional callable to fetch Contract by ID.
                Passed through to ContractYearDto.to_contract_year()

        Returns:
            Domain Monograph object
        """
        return Monograph(
            id=id or PublicationId(),
            title=NonEmptyStr(self.meta.title),
            license=License.of(self.meta.license),
            publication_type=self.meta.publication_type.to_concept(),
            subject_area=self.meta.subject_area.to_concept(),
            open_access_type=OpenAccessType[self.meta.open_access_type],
            publication_state=parse_publication_state(self.meta),
            relevant_authors=Authors(a.to_author() for a in self.relevant_authors),
            other_authors=AuthorNames(self.other_authors),
            links={link.to_link() for link in self.links},
            contracts=tuple(c.to_contract_year(get_contract_by_id) for c in self.contracts),
            publisher=self.publisher,
        )

    def to_publication(
        self, id: PublicationId | None = None, get_contract_by_id: GetContractById | None = None
    ) -> Monograph:
        return self.to_monograph(id, get_contract_by_id)


def parse_publication_state(publication: PublicationMetaDto) -> PublicationState:
    state = publication.publication_state

    if state.lower() == Published.name().lower():
        return Published(
            publication.online_publication_date,
            publication.print_publication_date,
        )
    else:
        return Unpublished.of(state)

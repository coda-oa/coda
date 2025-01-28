import datetime
import uuid
from typing import Annotated, Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from coda.apps.authors.dto import AuthorDto
from coda.apps.contracts import services as contract_services
from coda.apps.dto import CodaBaseDto, OptionalFromStr
from coda.author import AuthorNames
from coda.contract import ContractId, ContractYear, PublisherId
from coda.doi import Doi
from coda.publication import (
    Authors,
    JournalId,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
    UnpublishedState,
    UserLink,
)
from coda.string import NonEmptyStr
from coda.vocabulary import ConceptId, VocabularyConcept, VocabularyId


class LinkDto(CodaBaseDto):
    link_type: str
    link_value: str

    @classmethod
    def from_link(cls, link: Link) -> "LinkDto":
        match link:
            case UserLink(type, value):
                return LinkDto(link_type=type, link_value=value)
            case Doi(value):
                return LinkDto(link_type="DOI", link_value=value)

    def to_link(self) -> Link:
        if self.link_type == "DOI":
            return Doi(self.link_value)
        else:
            return UserLink(type=self.link_type, value=self.link_value)


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
    id: JournalId


class ContractIdAnnotation:
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        def validate_from_int(value: int) -> ContractId:
            return ContractId(value)

        from_int_schema = core_schema.chain_schema(
            [
                core_schema.int_schema(),
                core_schema.no_info_plain_validator_function(validate_from_int),
            ]
        )

        return core_schema.json_or_python_schema(
            json_schema=from_int_schema,
            python_schema=core_schema.union_schema(
                [core_schema.is_instance_schema(int), from_int_schema]
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(core_schema.int_schema())


class ContractYearDto(CodaBaseDto):
    contract: Annotated[ContractId, ContractIdAnnotation]
    year: int

    @classmethod
    def from_contract_year(cls, contract_year: ContractYear) -> "ContractYearDto":
        return cls(contract=contract_year.contract.id, year=contract_year.year)

    def to_contract_year(self) -> ContractYear:
        return contract_services.get_by_id(self.contract).in_year(self.year)


class PublicationBaseDto(CodaBaseDto):
    meta: PublicationMetaDto
    contracts: list[ContractYearDto]
    links: list[LinkDto]
    relevant_authors: list[AuthorDto]
    other_authors: list[str]


class PublicationDto(PublicationBaseDto):
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
            journal=JournalDto(id=publication.journal),
            contracts=[
                ContractYearDto(contract=c.contract.id, year=c.year) for c in publication.contracts
            ],
            links=[to_link_dto(link) for link in publication.links],
            relevant_authors=list(map(AuthorDto.from_author, publication.relevant_authors)),
            other_authors=list(publication.other_authors),
        )

    def to_publication(self, id: PublicationId | None = None) -> Publication:
        """
        Tries to parse a Publication from a PublicationDto.
        """
        return Publication(
            id=id,
            title=NonEmptyStr(self.meta.title),
            license=License[self.meta.license],
            publication_type=self.meta.publication_type.to_concept(),
            subject_area=self.meta.subject_area.to_concept(),
            open_access_type=OpenAccessType[self.meta.open_access_type],
            publication_state=_parse_state(self.meta),
            relevant_authors=Authors(a.to_author() for a in self.relevant_authors),
            other_authors=AuthorNames(self.other_authors),
            links={link.to_link() for link in self.links},
            contracts=tuple(c.to_contract_year() for c in self.contracts),
            journal=self.journal.id,
        )


class MonographDto(PublicationBaseDto):
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
            links=[to_link_dto(link) for link in publication.links],
            relevant_authors=list(map(AuthorDto.from_author, publication.relevant_authors)),
            other_authors=list(publication.other_authors),
        )

    def to_monograph(self, id: PublicationId | None = None) -> Monograph:
        """
        Tries to parse a Monograph from a MonographDto.
        """
        return Monograph(
            id=id,
            title=NonEmptyStr(self.meta.title),
            license=License[self.meta.license],
            publication_type=self.meta.publication_type.to_concept(),
            subject_area=self.meta.subject_area.to_concept(),
            open_access_type=OpenAccessType[self.meta.open_access_type],
            publication_state=_parse_state(self.meta),
            relevant_authors=Authors(a.to_author() for a in self.relevant_authors),
            other_authors=AuthorNames(self.other_authors),
            links={link.to_link() for link in self.links},
            contracts=tuple(c.to_contract_year() for c in self.contracts),
            publisher=self.publisher,
        )


def _parse_state(publication: PublicationMetaDto) -> PublicationState:
    state = publication.publication_state

    if state == Published.name():
        return Published(
            publication.online_publication_date,
            publication.print_publication_date,
        )
    else:
        return Unpublished(state=UnpublishedState[state])


def to_link_dto(link: Link) -> LinkDto:
    match link:
        case UserLink(type, value):
            return LinkDto(link_type=type, link_value=value)
        case Doi(value):
            return LinkDto(link_type="DOI", link_value=value)

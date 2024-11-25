import datetime

from coda.apps.authors.dto import AuthorDto
from coda.apps.dto import CodaBaseDto, OptionalFromStr
from coda.author import AuthorList
from coda.contract import ContractId
from coda.doi import Doi
from coda.publication import (
    JournalId,
    License,
    Link,
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
from coda.vocabulary import ConceptId, ConceptProtocol, VocabularyConcept, VocabularyId


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
    concept: ConceptId
    vocabulary: VocabularyId
    name: str = ""
    description: str = ""

    @classmethod
    def from_concept(cls, concept: ConceptProtocol) -> "ConceptDto":
        return cls(
            concept=concept.id,
            vocabulary=concept.vocabulary,
            name=concept.name,
            description=concept.description,
        )

    def to_concept(self) -> ConceptProtocol:
        return VocabularyConcept(
            id=ConceptId(self.concept),
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


class PublicationStepDto(CodaBaseDto):
    meta: PublicationMetaDto
    corresponding_author: AuthorDto
    authors: list[str]
    links: list[LinkDto]


class PublicationDto(CodaBaseDto):
    meta: PublicationMetaDto
    journal: JournalDto
    contracts: list[ContractId]
    links: list[LinkDto]
    corresponding_author: AuthorDto
    authors: list[str]

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
            contracts=list(publication.contracts),
            links=[to_link_dto(link) for link in publication.links],
            corresponding_author=AuthorDto.from_author(publication.corresponding_author),
            authors=list(publication.authors),
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
            corresponding_author=self.corresponding_author.to_author(),
            authors=AuthorList(self.authors),
            links={link.to_link() for link in self.links},
            contracts={ContractId(cid) for cid in self.contracts},
            journal=self.journal.id,
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

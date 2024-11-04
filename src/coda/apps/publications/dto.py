import datetime
from typing import Annotated, Any

from pydantic import BeforeValidator

from coda.apps.dto import CodaBaseDto
from coda.author import AuthorList
from coda.contract import ContractId
from coda.doi import Doi
from coda.publication import (
    ConceptId,
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
    VocabularyConcept,
    VocabularyId,
)
from coda.string import NonEmptyStr


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


def _validate_dates(value: Any) -> Any | None:
    if not value:
        return None

    return value


DateOrNonEmpty = Annotated[datetime.date | None, BeforeValidator(_validate_dates)]


class PublicationMetaDto(CodaBaseDto):
    title: str
    publication_type: str
    publication_type_vocabulary: int
    subject_area: str
    subject_area_vocabulary: int
    open_access_type: str
    license: str
    publication_state: str
    online_publication_date: DateOrNonEmpty
    print_publication_date: DateOrNonEmpty


class JournalDto(CodaBaseDto):
    id: JournalId


class PublicationDto(CodaBaseDto):
    meta: PublicationMetaDto
    journal: JournalDto
    contracts: list[ContractId]
    links: list[LinkDto]
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
                publication_type=publication.publication_type.id,
                publication_type_vocabulary=publication.publication_type.vocabulary,
                open_access_type=publication.open_access_type.name,
                publication_state=publication.publication_state.name(),
                online_publication_date=online_pub_date,
                print_publication_date=print_pub_date,
                subject_area=publication.subject_area.id,
                subject_area_vocabulary=publication.subject_area.vocabulary,
            ),
            journal=JournalDto(id=publication.journal),
            contracts=list(publication.contracts),
            links=[to_link_dto(link) for link in publication.links],
            authors=list(publication.authors),
        )

    def to_publication(self, id: PublicationId | None = None) -> Publication:
        """
        Tries to parse a Publication from a PublicationDto.
        """
        publication = self.meta
        return Publication(
            id=id,
            title=NonEmptyStr(publication.title),
            license=License[publication.license],
            publication_type=VocabularyConcept(
                ConceptId(publication.publication_type),
                VocabularyId(publication.publication_type_vocabulary),
            ),
            subject_area=VocabularyConcept(
                ConceptId(publication.subject_area),
                VocabularyId(publication.subject_area_vocabulary),
            ),
            open_access_type=OpenAccessType[publication.open_access_type],
            publication_state=_parse_state(publication),
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

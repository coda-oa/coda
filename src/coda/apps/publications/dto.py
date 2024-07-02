import datetime
from typing import Literal, TypedDict

from coda.apps.publications import services
from coda.author import AuthorList
from coda.doi import Doi
from coda.publication import (
    JournalId,
    License,
    Link,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    PublicationType,
    Published,
    Unpublished,
    UnpublishedState,
    UserLink,
)
from coda.string import NonEmptyStr


class LinkDto(TypedDict):
    link_type: str
    link_value: str


class PublicationMetaDto(TypedDict):
    title: str
    publication_type: str
    open_access_type: str
    license: str
    publication_state: str
    online_publication_date: str
    print_publication_date: str


class JournalDto(TypedDict):
    journal_id: int


class PublicationDto(TypedDict):
    meta: PublicationMetaDto
    journal: JournalDto
    links: list[LinkDto]
    authors: list[str]


def parse_publication(
    publication_dto: PublicationDto, id: PublicationId | None = None
) -> Publication:
    """
    Tries to parse a Publication from a PublicationDto.
    """
    publication = publication_dto["meta"]
    return Publication(
        id=id,
        title=NonEmptyStr(publication["title"]),
        license=License[publication["license"]],
        publication_type=PublicationType(publication["publication_type"]),
        open_access_type=OpenAccessType[publication["open_access_type"]],
        publication_state=_parse_state(publication),
        authors=AuthorList(publication_dto["authors"]),
        links={
            services.get_link(link["link_type"], link["link_value"])
            for link in publication_dto["links"]
        },
        journal=JournalId(publication_dto["journal"]["journal_id"]),
    )


DateKey = Literal["online_publication_date", "print_publication_date"]


def _parse_state(publication: PublicationMetaDto) -> PublicationState:
    state = publication["publication_state"]
    publication_state: PublicationState

    def __parse_date(key: DateKey) -> datetime.date | None:
        date_str = publication[key]
        return datetime.date.fromisoformat(date_str) if date_str else None

    if state == Published.name():
        online_date = __parse_date("online_publication_date")
        print_date = __parse_date("print_publication_date")
        publication_state = Published(online_date, print_date)
    else:
        publication_state = Unpublished(state=UnpublishedState[state])
    return publication_state


def to_publication_dto(publication: Publication) -> PublicationDto:
    online_pub_date, print_pub_date = _publication_dates_as_str(publication.publication_state)
    return PublicationDto(
        meta=PublicationMetaDto(
            title=publication.title,
            license=publication.license.name,
            publication_type=publication.publication_type,
            open_access_type=publication.open_access_type.name,
            publication_state=publication.publication_state.name(),
            online_publication_date=online_pub_date,
            print_publication_date=print_pub_date,
        ),
        journal=JournalDto(journal_id=publication.journal),
        links=[to_link_dto(link) for link in publication.links],
        authors=list(publication.authors),
    )


def _publication_dates_as_str(publication_state: PublicationState) -> tuple[str, str]:
    match publication_state:
        case Published(online, print_date):
            return (
                online.isoformat() if online else "",
                print_date.isoformat() if print_date else "",
            )
        case Unpublished(_):
            return "", ""


def to_link_dto(link: Link) -> LinkDto:
    match link:
        case UserLink(type, value):
            return LinkDto(link_type=type, link_value=value)
        case Doi(value):
            return LinkDto(link_type="DOI", link_value=value)

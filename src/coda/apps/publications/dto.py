import datetime
from typing import TypedDict

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


class PublicationDto(TypedDict):
    title: str
    publication_type: str
    open_access_type: str
    license: str
    publication_state: str
    online_publication_date: str | None
    print_publication_date: str | None
    links: list[LinkDto]
    journal: int
    authors: list[str]


def parse_publication(publication: PublicationDto, id: PublicationId | None = None) -> Publication:
    return Publication(
        id=id,
        title=NonEmptyStr(publication["title"]),
        authors=AuthorList(publication["authors"]),
        license=License[publication["license"]],
        publication_type=PublicationType(publication["publication_type"]),
        open_access_type=OpenAccessType[publication["open_access_type"]],
        publication_state=_parse_state(publication),
        links={
            services.get_link(link["link_type"], link["link_value"])
            for link in publication["links"]
        },
        journal=JournalId(publication["journal"]),
    )


def _parse_state(publication: PublicationDto) -> PublicationState:
    state = publication["publication_state"]
    publication_state: PublicationState
    if state == Published.name():
        online_date = (
            datetime.date.fromisoformat(publication["online_publication_date"])
            if publication["online_publication_date"]
            else None
        )
        print_date = (
            datetime.date.fromisoformat(publication["print_publication_date"])
            if publication["print_publication_date"]
            else None
        )

        publication_state = Published(online_date, print_date)
    else:
        publication_state = Unpublished(state=UnpublishedState[state])
    return publication_state


def _dates_from_publication_state(publication_state: PublicationState) -> tuple[str, str]:
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


def to_publication_dto(publication: Publication) -> PublicationDto:
    online_pub_date, print_pub_date = _dates_from_publication_state(publication.publication_state)
    return PublicationDto(
        title=publication.title,
        authors=list(publication.authors),
        license=publication.license.name,
        publication_type=publication.publication_type,
        open_access_type=publication.open_access_type.name,
        publication_state=publication.publication_state.name(),
        online_publication_date=online_pub_date,
        print_publication_date=print_pub_date,
        links=[to_link_dto(link) for link in publication.links],
        journal=publication.journal,
    )

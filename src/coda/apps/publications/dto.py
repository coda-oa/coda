import datetime
from typing import Literal, TypedDict, cast

from coda.apps.publications import services
from coda.apps.publications.models import Publication as PublicationModel
from coda.author import AuthorList
from coda.publication import (
    JournalId,
    License,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    PublicationType,
    Published,
    UnknownPublicationType,
    Unpublished,
    UnpublishedState,
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


DateLiteral = Literal["online_publication_date", "print_publication_date"]


def _datekey(media: str) -> DateLiteral:
    return cast(DateLiteral, f"{media}_publication_date")


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


def publication_dto_from_model(publication: PublicationModel) -> PublicationDto:
    return PublicationDto(
        title=publication.title,
        authors=list(publication.authors),
        license=publication.license,
        publication_type=(
            publication.publication_type.concept_id
            if publication.publication_type
            else UnknownPublicationType
        ),
        open_access_type=publication.open_access_type,
        publication_state=publication.publication_state,
        online_publication_date=(
            publication.online_publication_date.isoformat()
            if publication.online_publication_date
            else ""
        ),
        print_publication_date=(
            publication.print_publication_date.isoformat()
            if publication.print_publication_date
            else ""
        ),
        links=[
            LinkDto(link_type=link.type.name, link_value=link.value)
            for link in publication.links.all()
        ],
        journal=publication.journal.pk,
    )

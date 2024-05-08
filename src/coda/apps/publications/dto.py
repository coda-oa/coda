import datetime
from typing import TypedDict, cast

from coda.apps.publications.models import Publication as PublicationModel
from coda.author import AuthorList
from coda.publication import (
    JournalId,
    License,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    UnpublishedState,
    Unpublished,
    UserLink,
)
from coda.string import NonEmptyStr


class LinkDto(TypedDict):
    link_type: str
    link_value: str


class PublicationDto(TypedDict):
    title: str
    open_access_type: str
    license: str
    publication_state: str
    publication_date: datetime.date | None
    links: list[LinkDto]
    journal: int
    authors: list[str]


def parse_publication(publication: PublicationDto, id: PublicationId | None = None) -> Publication:
    state = publication["publication_state"]
    publication_state: PublicationState
    if state == Published.name():
        # NOTE: We are casting here because the Published constructor will take care of validating the date
        publication_state = Published(date=cast(datetime.date, publication["publication_date"]))
    else:
        publication_state = Unpublished(state=UnpublishedState[state])

    return Publication(
        id=id,
        title=NonEmptyStr(publication["title"]),
        authors=AuthorList(publication["authors"]),
        license=License[publication["license"]],
        open_access_type=OpenAccessType[publication["open_access_type"]],
        publication_state=publication_state,
        links={UserLink(link["link_type"], link["link_value"]) for link in publication["links"]},
        journal=JournalId(publication["journal"]),
    )


def publication_dto_from_model(publication: PublicationModel) -> PublicationDto:
    return PublicationDto(
        title=publication.title,
        authors=list(publication.authors),
        license=publication.license,
        open_access_type=publication.open_access_type,
        publication_state=publication.publication_state,
        publication_date=publication.publication_date,
        links=[
            LinkDto(link_type=link.type.name, link_value=link.value)
            for link in publication.links.all()
        ],
        journal=publication.journal.pk,
    )

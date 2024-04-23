import datetime
from typing import TypedDict

from coda.apps.publications.models import Publication
from coda.author import AuthorList


class LinkDto(TypedDict):
    link_type: int
    link_value: str


class PublicationDto(TypedDict):
    title: str
    open_access_type: str
    license: str
    publication_state: str
    publication_date: datetime.date | None
    links: list[LinkDto]
    journal: int
    authors: AuthorList


def publication_dto_from_model(publication: Publication) -> PublicationDto:
    return PublicationDto(
        title=publication.title,
        authors=publication.authors,
        license=publication.license,
        open_access_type=publication.open_access_type,
        publication_state=publication.publication_state,
        publication_date=publication.publication_date,
        links=[
            LinkDto(link_type=link.type.pk, link_value=link.value)
            for link in publication.links.all()
        ],
        journal=publication.journal.pk,
    )

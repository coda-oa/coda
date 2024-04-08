from typing import TypedDict

from coda.apps.publications.models import Publication


class LinkDto(TypedDict):
    link_type: int
    link_value: str


class PublicationDto(TypedDict):
    title: str
    open_access_type: str
    publication_state: str
    publication_date: str
    links: list[LinkDto]
    journal: int


def publication_dto_from_model(publication: Publication) -> PublicationDto:
    return PublicationDto(
        title=publication.title,
        open_access_type=publication.open_access_type,
        publication_state=publication.publication_state,
        publication_date=publication.publication_date.isoformat()
        if publication.publication_date
        else "",
        links=[
            LinkDto(link_type=link.type.pk, link_value=link.value)
            for link in publication.links.all()
        ],
        journal=publication.journal.pk,
    )

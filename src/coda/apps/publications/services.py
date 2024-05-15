import datetime
from collections.abc import Iterable
from dataclasses import replace
from typing import cast

from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.models import LinkType
from coda.apps.publications.models import Publication as PublicationModel
from coda.author import AuthorId, AuthorList
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


def _deserialize_links(links: Iterable[LinkModel]) -> set[Link]:
    return {get_link(link.type.name, link.value) for link in links}


def get_link(link_type: str, value: str) -> Link:
    if link_type == "DOI":
        return Doi(value)
    else:
        return UserLink(type=link_type, value=value)


def get_by_id(publication_id: PublicationId) -> Publication:
    model = PublicationModel.objects.get(pk=publication_id)
    state = _deserialize_publication_state(model)

    return Publication(
        id=publication_id,
        title=NonEmptyStr(model.title),
        license=License[model.license],
        open_access_type=OpenAccessType[model.open_access_type],
        authors=AuthorList.from_str(model.author_list or ""),
        publication_state=state,
        journal=JournalId(model.journal_id),
        links=_deserialize_links(model.links.all()),
    )


def _deserialize_publication_state(model: PublicationModel) -> PublicationState:
    state: PublicationState
    if model.publication_state == "Published":
        state = Published(date=cast(datetime.date, model.publication_date))
    else:
        state = Unpublished(state=UnpublishedState[model.publication_state])
    return state


def publication_create(publication: Publication, author_id: AuthorId) -> PublicationId:
    publication_date = None
    if isinstance(publication.publication_state, Published):
        publication_date = publication.publication_state.date

    pub_model = PublicationModel.objects.create(
        title=publication.title,
        license=publication.license.name,
        open_access_type=publication.open_access_type.name,
        publication_state=publication.publication_state.name(),
        publication_date=publication_date,
        submitting_author_id=author_id,
        author_list=str(publication.authors),
        journal_id=publication.journal,
    )
    publication = replace(publication, id=PublicationId(pub_model.id))
    _attach_links(publication)
    return cast(PublicationId, publication.id)


def publication_update(publication: Publication) -> None:
    if not publication.id:
        raise ValueError("Publication ID is required for updating")

    if isinstance(publication.publication_state, Published):
        publication_state = publication.publication_state.name()
        publication_date = publication.publication_state.date
    else:
        publication_state = publication.publication_state.state.name
        publication_date = None

    PublicationModel.objects.filter(pk=publication.id).update(
        title=publication.title,
        license=publication.license.name,
        open_access_type=publication.open_access_type.name,
        author_list=str(publication.authors),
        publication_state=publication_state,
        publication_date=publication_date,
        journal_id=publication.journal,
    )

    LinkModel.objects.filter(publication_id=publication.id).all().delete()
    _attach_links(publication)


def _attach_links(publication: Publication) -> None:
    for link in publication.links:
        if isinstance(link, Doi):
            link_type = "DOI"
            link_value = str(link)
        else:
            link_type = link.type
            link_value = link.value

        LinkModel.objects.create(
            value=link_value,
            type=LinkType.objects.get(name=link_type),
            publication_id=cast(int, publication.id),
        )

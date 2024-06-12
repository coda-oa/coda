import datetime
from collections.abc import Iterable
from dataclasses import replace
from typing import cast

from coda.apps.publications.models import Concept, LinkType
from coda.apps.publications.models import Link as LinkModel
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
    PublicationType,
    Published,
    UnknownPublicationType,
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
        publication_type=_deserialize_publication_type(model),
        authors=AuthorList.from_str(model.author_list or ""),
        publication_state=state,
        journal=JournalId(model.journal_id),
        links=_deserialize_links(model.links.all()),
    )


def _deserialize_publication_type(model: PublicationModel) -> PublicationType:
    if model.publication_type is None:
        publication_type = UnknownPublicationType
    else:
        publication_type = PublicationType(model.publication_type.concept_id)

    return publication_type


def _deserialize_publication_state(model: PublicationModel) -> PublicationState:
    state: PublicationState
    if getattr(model, "publication_state") == Published.name():
        state = Published(online=model.online_publication_date, print=model.print_publication_date)
    else:
        state = Unpublished(state=UnpublishedState[model.publication_state])
    return state


def publication_create(publication: Publication, author_id: AuthorId) -> PublicationId:
    online_publication_date = None
    if isinstance(publication.publication_state, Published):
        online_publication_date = publication.publication_state.online
        print_publication_date = publication.publication_state.print
    else:
        online_publication_date = None
        print_publication_date = None

    concept = Concept.objects.filter(concept_id=publication.publication_type).first()

    pub_model = PublicationModel.objects.create(
        title=publication.title,
        license=publication.license.name,
        open_access_type=publication.open_access_type.name,
        publication_state=publication.publication_state.name(),
        online_publication_date=online_publication_date,
        print_publication_date=print_publication_date,
        submitting_author_id=author_id,
        author_list=str(publication.authors),
        journal_id=publication.journal,
        publication_type=concept,
    )
    publication = replace(publication, id=PublicationId(pub_model.id))
    _attach_links(publication)
    return cast(PublicationId, publication.id)


def publication_update(publication: Publication) -> None:
    if not publication.id:
        raise ValueError("Publication ID is required for updating")

    publication_state = publication.publication_state.name()
    if isinstance(publication.publication_state, Published):
        online_publication_date = publication.publication_state.online
        print_publication_date = publication.publication_state.print
    else:
        online_publication_date = None
        print_publication_date = None

    concept = Concept.objects.filter(concept_id=publication.publication_type).first()
    PublicationModel.objects.filter(pk=publication.id).update(
        title=publication.title,
        license=publication.license.name,
        open_access_type=publication.open_access_type.name,
        author_list=str(publication.authors),
        publication_state=publication_state,
        online_publication_date=online_publication_date,
        print_publication_date=print_publication_date,
        journal_id=publication.journal,
        publication_type=concept,
    )

    LinkModel.objects.filter(publication_id=publication.id).all().delete()
    _attach_links(publication)


def _serializable_publication_state(state: PublicationState) -> tuple[str, datetime.date | None]:
    if isinstance(state, Published):
        publication_state = state.name()
        publication_date = state.online
    else:
        publication_state = state.state.name
        publication_date = None

    return publication_state, publication_date


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

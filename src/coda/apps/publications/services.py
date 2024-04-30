from dataclasses import replace
from typing import cast

from coda.apps.publications.models import Link, LinkType
from coda.apps.publications.models import Publication as PublicationModel
from coda.author import AuthorId
from coda.doi import Doi
from coda.publication import Publication, PublicationId, Published


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

    Link.objects.filter(publication_id=publication.id).all().delete()
    _attach_links(publication)


def _attach_links(publication: Publication) -> None:
    for link in publication.links:
        if isinstance(link, Doi):
            link_type = "DOI"
            link_value = str(link)
        else:
            link_type = link.type
            link_value = link.value

        Link.objects.create(
            value=link_value,
            type=LinkType.objects.get(name=link_type),
            publication_id=cast(int, publication.id),
        )

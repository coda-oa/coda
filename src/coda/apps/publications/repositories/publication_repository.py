from collections.abc import Iterable
from typing import cast

from coda.apps.authors import services as author_services
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import PersonId
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.models import LinkType
from coda.apps.publications.models import Publication as PublicationModel
from coda.author import AuthorId, AuthorList
from coda.contract import ContractId
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
)
from coda.string import NonEmptyStr
from coda.vocabulary import UnknownConcept


def save(publication: Publication) -> None:
    if publication.id:
        p = PublicationModel.objects.get(pk=publication.id)
        p.journal_id = publication.journal
    else:
        p = PublicationModel.objects.create(journal_id=publication.journal)

    p.title = publication.title
    p.license = publication.license.name
    p.open_access_type = publication.open_access_type.name
    p.author_list = str(publication.authors)
    p.publication_state = publication.publication_state.name()
    _attach_links(PublicationId(p.id), publication.links)

    if publication.is_published():
        publication_state = cast(Published, publication.publication_state)
        p.online_publication_date = publication_state.online
        p.print_publication_date = publication_state.print

    p.publication_type = None
    p.subject_area = None
    p.contracts.set(publication.contracts)

    if not p.submitting_author:
        p.submitting_author = AuthorModel()

    p.submitting_author.name = publication.corresponding_author.name
    p.submitting_author.email = publication.corresponding_author.email
    p.submitting_author.affiliation_id = publication.corresponding_author.affiliation

    if not p.submitting_author.identifier:
        p.submitting_author.identifier = PersonId()

    p.submitting_author.identifier.orcid = publication.corresponding_author.orcid
    p.submitting_author.identifier.save()

    p.submitting_author.save()
    p.save()


def first() -> Publication | None:
    p = PublicationModel.objects.first()
    if not p:
        return None

    return as_domain_object(p)


def as_domain_object(model: PublicationModel) -> Publication:
    state = _deserialize_publication_state(model)

    return Publication(
        id=PublicationId(model.pk),
        title=NonEmptyStr(model.title),
        license=License[model.license],
        open_access_type=OpenAccessType[model.open_access_type],
        publication_type=UnknownConcept,
        subject_area=UnknownConcept,
        corresponding_author=author_services.get_by_id(
            AuthorId(cast(int, model.submitting_author_id))
        ),
        authors=AuthorList.from_str(model.author_list or ""),
        publication_state=state,
        journal=JournalId(model.journal_id),
        contracts={ContractId(c.pk) for c in model.contracts.all()},
        links=_deserialize_links(model.links.all()),
    )


def _deserialize_publication_state(model: PublicationModel) -> PublicationState:
    state: PublicationState
    if getattr(model, "publication_state") == Published.name():
        state = Published(online=model.online_publication_date, print=model.print_publication_date)
    else:
        state = Unpublished(state=UnpublishedState[model.publication_state])
    return state


def _deserialize_links(links: Iterable[LinkModel]) -> set[Link]:
    return {LinkDto(link_type=link.type.name, link_value=link.value).to_link() for link in links}


def _attach_links(id: PublicationId, links: Iterable[Link]) -> None:
    for link in links:
        if isinstance(link, Doi):
            link_type = "DOI"
            link_value = str(link)
        else:
            link_type = link.type
            link_value = link.value

        LinkModel.objects.create(
            value=link_value,
            type=LinkType.objects.get(name=link_type),
            publication_id=cast(int, id),
        )

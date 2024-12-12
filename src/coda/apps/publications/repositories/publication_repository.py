from collections.abc import Iterable
from typing import cast

from django.db import transaction

from coda.apps.authors import services as author_services
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.models import LinkType, PublicationAttachedConcept
from coda.apps.publications.models import Publication as PublicationModel
from coda.apps.publications.repositories import vocabulary_repository
from coda.author import AuthorId, AuthorList
from coda.contract import ContractId, PublisherId
from coda.doi import Doi
from coda.publication import (
    BasePublication,
    JournalId,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
    UnpublishedState,
)
from coda.string import NonEmptyStr
from coda.vocabulary import ConceptId, UnknownConcept, VocabularyConcept, VocabularyId


def _initial_article(publication: Publication) -> PublicationModel:
    if publication.id:
        p = PublicationModel.objects.get(pk=publication.id)
        p.article_journal_id = publication.journal
    else:
        p = PublicationModel.objects.create(article_journal_id=publication.journal)

    return p


def _initial_monograph(publication: Monograph) -> PublicationModel:
    if publication.id:
        p = PublicationModel.objects.get(pk=publication.id)
        p.monograph_publisher_id = publication.publisher
    else:
        p = PublicationModel.objects.create(monograph_publisher_id=publication.publisher)

    return p


@transaction.atomic
def save(publication: BasePublication) -> PublicationId:
    match publication:
        case Publication():
            p = _initial_article(publication)
        case Monograph():
            p = _initial_monograph(publication)
        case _:
            raise ValueError("Unknown publication type")

    p.title = publication.title
    p.license = publication.license.name
    p.open_access_type = publication.open_access_type.name
    p.author_list = str(publication.authors)
    p.publication_state = publication.publication_state.name()
    p.links.all().delete()
    _attach_links(PublicationId(p.id), publication.links)

    if publication.is_published():
        publication_state = cast(Published, publication.publication_state)
        p.online_publication_date = publication_state.online
        p.print_publication_date = publication_state.print

    p.publication_type.entity_id = publication.publication_type.id
    p.publication_type.vocabulary_id = publication.publication_type.vocabulary
    p.publication_type.name = publication.publication_type.name
    p.publication_type.save()

    p.subject_area.entity_id = publication.subject_area.id
    p.subject_area.vocabulary_id = publication.subject_area.vocabulary
    p.subject_area.name = publication.subject_area.name
    p.subject_area.save()

    p.contracts.set(publication.contracts)

    if not p.submitting_author:
        author_id = author_services.author_create(publication.corresponding_author)
        p.submitting_author_id = author_id
    else:
        publication.corresponding_author.id = AuthorId(p.submitting_author.id)
        author_services.author_update(publication.corresponding_author)

    p.save()
    return PublicationId(p.pk)


def get_by_id(publication_id: PublicationId) -> BasePublication:
    model = PublicationModel.objects.get(pk=publication_id)
    return as_domain_object(model)


def first() -> BasePublication | None:
    p = PublicationModel.objects.first()
    if not p:
        return None

    return as_domain_object(p)


def as_domain_object(model: PublicationModel) -> BasePublication:
    state = _deserialize_publication_state(model)

    if model.article_journal_id:
        return Publication(
            id=PublicationId(model.pk),
            title=NonEmptyStr(model.title),
            license=License[model.license],
            open_access_type=OpenAccessType[model.open_access_type],
            publication_type=_deserialize_concept(model.publication_type),
            subject_area=_deserialize_concept(model.subject_area),
            corresponding_author=author_services.get_by_id(
                AuthorId(cast(int, model.submitting_author_id))
            ),
            authors=AuthorList.from_str(model.author_list or ""),
            publication_state=state,
            journal=JournalId(model.article_journal_id),
            contracts={ContractId(c.pk) for c in model.contracts.all()},
            links=_deserialize_links(model.links.all()),
        )
    elif model.monograph_publisher_id:
        return Monograph(
            id=PublicationId(model.pk),
            title=NonEmptyStr(model.title),
            license=License[model.license],
            open_access_type=OpenAccessType[model.open_access_type],
            publication_type=_deserialize_concept(model.publication_type),
            subject_area=_deserialize_concept(model.subject_area),
            corresponding_author=author_services.get_by_id(
                AuthorId(cast(int, model.submitting_author_id))
            ),
            authors=AuthorList.from_str(model.author_list or ""),
            publication_state=state,
            publisher=PublisherId(model.monograph_publisher_id),
            contracts={ContractId(c.pk) for c in model.contracts.all()},
            links=_deserialize_links(model.links.all()),
        )
    else:
        raise ValueError("Unknown publication type")


def _deserialize_publication_state(model: PublicationModel) -> PublicationState:
    state: PublicationState
    if getattr(model, "publication_state") == Published.name():
        state = Published(online=model.online_publication_date, print=model.print_publication_date)
    else:
        state = Unpublished(state=UnpublishedState[model.publication_state])
    return state


def _deserialize_concept(model_concept: PublicationAttachedConcept) -> VocabularyConcept:
    if model_concept.entity_id == UnknownConcept.id:
        return UnknownConcept

    v = vocabulary_repository.get_by_id(cast(VocabularyId, model_concept.vocabulary_id))
    return v.get_concept_by_id(ConceptId(str(model_concept.entity_id)))


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

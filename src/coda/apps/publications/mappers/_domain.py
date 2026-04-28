import dataclasses
from collections.abc import Iterable
from typing import Any, TypeVar, cast

from django.db.models import Model, Prefetch, QuerySet

from coda.apps.authors.mappers._domain import AuthorDomainMapper
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.contracts import mapper as contract_mapper
from coda.apps.mappers import prefixed
from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.models import Publication as PublicationModel
from coda.apps.publications.models import PublicationAttachedConcept
from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.domain.author import AuthorNames
from coda.domain.contract import ContractYear, PublisherId
from coda.domain.publication import (
    Authors,
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
    links,
)
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    UnknownConcept,
    VocabularyConcept,
    VocabularyId,
)

from ._vocabulary import VocabularyDomainMapper

_T = TypeVar("_T", bound=Model)


class PublicationDomainMapper:
    @staticmethod
    def prefetch(qs: QuerySet[_T], prefix: str = "") -> QuerySet[_T]:
        qs = qs.select_related(
            prefixed(prefix, "article_journal"),
            prefixed(prefix, "article_journal__publisher"),
            prefixed(prefix, "monograph_publisher"),
            prefixed(prefix, "publication_type"),
            prefixed(prefix, "subject_area"),
        )
        qs = qs.prefetch_related(
            Prefetch(
                prefixed(prefix, "publication_type__vocabulary"),
                queryset=VocabularyDomainMapper.prefetch(VocabularyModel.objects.all()),
            ),
            Prefetch(
                prefixed(prefix, "subject_area__vocabulary"),
                queryset=VocabularyDomainMapper.prefetch(VocabularyModel.objects.all()),
            ),
            Prefetch(
                prefixed(prefix, "relevant_authors"),
                queryset=AuthorDomainMapper.prefetch(AuthorModel.objects.all()),
            ),
            prefixed(prefix, "attached_contracts"),
            prefixed(prefix, "links__type"),
        )
        return qs

    @staticmethod
    def map(model: PublicationModel) -> BasePublication:
        common_args = _common_args(model)
        if model.article_journal_id:
            return Publication(
                **common_args,
                journal=JournalId(model.article_journal_id),
            )
        elif model.monograph_publisher_id:
            return Monograph(
                **common_args,
                publisher=PublisherId(model.monograph_publisher_id),
            )
        else:
            raise ValueError("Unknown publication type")


def _common_args(model: PublicationModel) -> dict[str, Any]:
    return dict(
        id=PublicationId(model.pk),
        title=NonEmptyStr(model.title),
        license=License[model.license],
        open_access_type=OpenAccessType[model.open_access_type],
        publication_type=_deserialize_concept(model.publication_type),
        subject_area=_deserialize_concept(model.subject_area),
        relevant_authors=Authors(AuthorDomainMapper.map(a) for a in model.relevant_authors.all()),
        other_authors=AuthorNames.from_str(model.author_list or ""),
        publication_state=_deserialize_publication_state(model),
        contracts=tuple(
            ContractYear(c.contract_year, contract_mapper.as_domain_object(c.contract))
            for c in model.attached_contracts.order_by("id")
        ),
        links=_deserialize_links(model.links.all()),
    )


def _deserialize_publication_state(model: PublicationModel) -> PublicationState:
    if getattr(model, "publication_state") == Published.name():
        return Published(online=model.online_publication_date, print=model.print_publication_date)
    return Unpublished(state=UnpublishedState[model.publication_state])


def _deserialize_concept(model_concept: PublicationAttachedConcept) -> VocabularyConcept:
    if model_concept.entity_id == UnknownConcept.id:
        return UnknownConcept

    v = VocabularyDomainMapper.map(model_concept.vocabulary)
    concept_id = ConceptId(str(model_concept.entity_id))
    vocabulary_id = cast(VocabularyId, model_concept.vocabulary_id)

    if isinstance(v, LimitedVocabulary):
        concept = v.get_root_base_vocabulary().get_concept_by_id(concept_id)
        return dataclasses.replace(concept, vocabulary=vocabulary_id)

    return v.get_concept_by_id(concept_id)


def _deserialize_links(links_: Iterable[LinkModel]) -> set[Link]:
    return {links.create_link(link_type=link.type.name, link_value=link.value) for link in links_}

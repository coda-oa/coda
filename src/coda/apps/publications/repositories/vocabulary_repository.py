from typing import Any, cast

from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    Vocabulary,
    VocabularyId,
    VocabularyProtocol,
)


class EntityNotFoundError(Exception):
    def __init__(self, entity_type: type[Any], query_name: str, query_value: Any) -> None:
        super().__init__(f"{entity_type.__name__} with {query_name}={query_value} not found")
        self.entity_type = entity_type
        self.query_name = query_name
        self.query_value = query_value


def get_by_id(id: VocabularyId) -> VocabularyProtocol:
    try:
        v = VocabularyModel.objects.get(pk=id)
    except VocabularyModel.DoesNotExist:
        raise EntityNotFoundError(Vocabulary, query_name="id", query_value=id)

    vocabulary = as_domain_object(v)

    return vocabulary


def first_by_name(name: str) -> VocabularyProtocol:
    try:
        v = VocabularyModel.objects.get(name=name)
    except VocabularyModel.DoesNotExist:
        raise EntityNotFoundError(Vocabulary, query_name="name", query_value=name)

    return as_domain_object(v)


def all() -> list[VocabularyProtocol]:
    return [as_domain_object(v) for v in VocabularyModel.objects.all()]


def save(vocabulary: VocabularyProtocol) -> None:
    v, _ = VocabularyModel.objects.get_or_create(pk=vocabulary.id)
    v.name = vocabulary.name
    v.version = vocabulary.version

    if isinstance(vocabulary, Vocabulary):
        concepts = vocabulary.concepts
    elif isinstance(vocabulary, LimitedVocabulary):
        concepts = vocabulary.disallowed_concepts
        v.is_limited = True
        v.base_vocabulary_id = vocabulary.vocabulary.id
    else:
        raise ValueError(f"Unsupported vocabulary type: {type(vocabulary)}")

    for c in concepts:
        mc, _ = v.concepts.get_or_create(concept_id=c.id)
        mc.name = c.name
        mc.hint = c.description
        mc.is_allowed = c.is_allowed
        mc.save()

    v.save()


def as_domain_object(v: VocabularyModel) -> VocabularyProtocol:
    vocabulary: VocabularyProtocol

    if v.is_limited:
        base_vocabulary = cast(VocabularyModel, v.base_vocabulary)
        base_vocabulary_domain = as_domain_object(base_vocabulary)
        vocabulary = LimitedVocabulary(id=VocabularyId(v.pk), vocabulary=base_vocabulary_domain)
        for c in v.concepts.all():
            vocabulary.disallow(ConceptId(c.concept_id))
    else:
        vocabulary = Vocabulary(id=VocabularyId(v.pk), name=v.name, version=v.version)
        for c in v.concepts.all():
            vocabulary.add_concept(
                id=ConceptId(c.concept_id), name=c.name, description=c.hint, is_allowed=c.is_allowed
            )

    return vocabulary

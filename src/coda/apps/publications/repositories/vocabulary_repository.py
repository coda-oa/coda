from typing import Any

from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.vocabulary import ConceptId, Vocabulary, VocabularyId


class EntityNotFoundError(Exception):
    def __init__(self, entity_type: type[Any], query_name: str, query_value: Any) -> None:
        super().__init__(f"{entity_type.__name__} with {query_name}={query_value} not found")
        self.entity_type = entity_type
        self.query_name = query_name
        self.query_value = query_value


def get_by_id(id: VocabularyId) -> Vocabulary:
    try:
        v = VocabularyModel.objects.get(pk=id)
    except VocabularyModel.DoesNotExist:
        raise EntityNotFoundError(Vocabulary, query_name="id", query_value=id)

    vocabulary = as_domain_object(v)

    return vocabulary


def first_by_name(name: str) -> Vocabulary:
    try:
        v = VocabularyModel.objects.get(name=name)
    except VocabularyModel.DoesNotExist:
        raise EntityNotFoundError(Vocabulary, query_name="name", query_value=name)

    return as_domain_object(v)


def all() -> list[Vocabulary]:
    return [as_domain_object(v) for v in VocabularyModel.objects.all()]


def save(vocabulary: Vocabulary) -> None:
    v, _ = VocabularyModel.objects.get_or_create(pk=vocabulary.id)
    v.name = vocabulary.name
    v.version = vocabulary.version
    v.save()

    for c in vocabulary.concepts:
        mc, _ = v.concepts.get_or_create(concept_id=c.id)
        mc.name = c.name
        mc.hint = c.description
        mc.is_allowed = c.is_allowed
        mc.save()


def as_domain_object(v: VocabularyModel) -> Vocabulary:
    vocabulary = Vocabulary(id=VocabularyId(v.pk), name=v.name, version=v.version)
    for c in v.concepts.all():
        vocabulary.add_concept(
            id=ConceptId(c.concept_id), name=c.name, description=c.hint, is_allowed=c.is_allowed
        )

    return vocabulary

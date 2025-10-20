from collections.abc import Collection, Sequence
from typing import Any, cast

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.apps.publications.repositories import publication_repository
from coda.domain.errors import DomainError
from coda.domain.publication import BasePublication
from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
    VocabularyProtocol,
)


class VocabularyNotFoundError(DomainError):
    def __init__(self, entity_type: type[Any], query_name: str, query_value: Any) -> None:
        super().__init__(f"{entity_type.__name__} with {query_name}={query_value} not found")
        self.entity_type = entity_type
        self.query_name = query_name
        self.query_value = query_value


class VocabularyInUseError(DomainError):
    def __init__(
        self,
        vocabulary: VocabularyProtocol,
        publications: list[BasePublication] | None = None,
        limited_vocabularies: list[LimitedVocabulary] | None = None,
    ) -> None:
        super().__init__(f"Vocabulary {vocabulary.id} is in use")
        self.vocabulary = vocabulary
        self.publications = publications or []
        self.limited_vocabularies = limited_vocabularies or []


def create(name: str, version: str) -> Vocabulary:
    return cast(
        Vocabulary,
        as_domain_object(VocabularyModel.objects.create(name=name, version=version)),
    )


def create_limited(base_vocabulary_id: VocabularyId, name: str) -> LimitedVocabulary:
    base_vocabulary = get_by_id(base_vocabulary_id)
    return cast(
        LimitedVocabulary,
        as_domain_object(
            VocabularyModel.objects.create(
                name=name,
                version=base_vocabulary.version,
                is_limited=True,
                base_vocabulary_id=base_vocabulary.id,
            )
        ),
    )


def get_by_id(id: VocabularyId) -> VocabularyProtocol:
    try:
        v = VocabularyModel.objects.get(pk=id)
    except VocabularyModel.DoesNotExist:
        raise VocabularyNotFoundError(Vocabulary, query_name="id", query_value=id)

    vocabulary = as_domain_object(v)

    return vocabulary


def get_limited_by_id(id: VocabularyId) -> LimitedVocabulary:
    v = get_by_id(id)
    if not isinstance(v, LimitedVocabulary):
        raise VocabularyNotFoundError(LimitedVocabulary, query_name="id", query_value=id)

    return v


def first_by_name(name: str) -> VocabularyProtocol:
    try:
        v = VocabularyModel.objects.get(name=name)
    except VocabularyModel.DoesNotExist:
        raise VocabularyNotFoundError(Vocabulary, query_name="name", query_value=name)

    return as_domain_object(v)


def newest_base_vocabulary_by_name(name: str) -> Vocabulary:
    vocabularies_by_name = VocabularyModel.objects.filter(name=name, is_limited=False)
    vocabularies_by_name = vocabularies_by_name.order_by("-version")

    v = vocabularies_by_name.first()
    if not v:
        raise VocabularyNotFoundError(Vocabulary, query_name="name", query_value=name)

    return cast(Vocabulary, as_domain_object(v))


def find_limited_by_base_vocabulary(base_vocabulary_id: VocabularyId) -> list[LimitedVocabulary]:
    return [
        cast(LimitedVocabulary, as_domain_object(v))
        for v in VocabularyModel.objects.filter(base_vocabulary_id=base_vocabulary_id)
    ]


def all() -> Sequence[VocabularyProtocol]:
    return DomainQuerySet(VocabularyModel.objects.all(), as_domain_object)


def all_limited() -> list[LimitedVocabulary]:
    return [
        cast(LimitedVocabulary, as_domain_object(v))
        for v in VocabularyModel.objects.filter(is_limited=True)
    ]


def save(vocabulary: VocabularyProtocol) -> None:
    v, _ = VocabularyModel.objects.get_or_create(pk=vocabulary.id)
    v.name = vocabulary.name
    v.version = vocabulary.version

    concepts: Collection[VocabularyConcept]
    if isinstance(vocabulary, Vocabulary):
        concepts = vocabulary.concepts
    elif isinstance(vocabulary, LimitedVocabulary):
        concepts = vocabulary.disallowed_concepts
        v.is_limited = True
        v.base_vocabulary_id = vocabulary.base_vocabulary.id
        v.concepts.all().delete()
    else:
        raise ValueError(f"Unsupported vocabulary type: {type(vocabulary)}")

    for c in concepts:
        mc, _ = v.concepts.get_or_create(entity_id=c.id)
        mc.concept_id = c.concept_id
        mc.name = c.name
        mc.hint = c.description
        mc.save()

    v.save()


def delete(vocabulary: VocabularyProtocol) -> None:
    id = vocabulary.id
    publications = publication_repository.find_publications_by_vocabulary(id)
    limited_vocabularies = find_limited_by_base_vocabulary(id)
    if publications or limited_vocabularies:
        raise VocabularyInUseError(
            vocabulary=vocabulary,
            publications=publications,
            limited_vocabularies=limited_vocabularies,
        )

    VocabularyModel.objects.get(pk=id).delete()


def as_domain_object(v: VocabularyModel) -> VocabularyProtocol:
    vocabulary: VocabularyProtocol

    if v.is_limited:
        base_vocabulary = cast(VocabularyModel, v.base_vocabulary)
        base_vocabulary_domain = as_domain_object(base_vocabulary)
        vocabulary = LimitedVocabulary(
            id=VocabularyId(v.pk),
            base_vocabulary=base_vocabulary_domain,
            name=v.name,
            version=base_vocabulary.version,
        )
        for c in v.concepts.all():
            vocabulary.disallow(c.concept_id)
    else:
        vocabulary = Vocabulary(
            id=VocabularyId(v.pk),
            name=v.name,
            version=v.version,
            concepts=[
                VocabularyConcept(
                    id=ConceptId(str(c.entity_id)),
                    concept_id=c.concept_id,
                    vocabulary=VocabularyId(v.pk),
                    name=c.name,
                    description=c.hint,
                    parent=ConceptId(str(c.parent.entity_id)) if c.parent else None,
                )
                for c in v.concepts.all()
            ],
        )

    return vocabulary

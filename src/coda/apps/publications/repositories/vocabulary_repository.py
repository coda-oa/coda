from collections.abc import Collection, Sequence
from typing import Any, cast

from django.db.models import Prefetch

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.publications.models import Concept as ConceptModel
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


def _get_prefetch_for_vocabularies() -> tuple[Prefetch, Prefetch]:
    concepts_prefetch = Prefetch(
        "concepts",
        queryset=ConceptModel.objects.select_related("parent"),
    )
    base_vocab_prefetch = Prefetch(
        "base_vocabulary",
        queryset=VocabularyModel.objects.prefetch_related(
            Prefetch("concepts", queryset=ConceptModel.objects.select_related("parent"))
        ),
    )
    return concepts_prefetch, base_vocab_prefetch


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
        concepts_prefetch, base_vocab_prefetch = _get_prefetch_for_vocabularies()
        v = VocabularyModel.objects.prefetch_related(
            concepts_prefetch,
            base_vocab_prefetch,
        ).get(pk=id)
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
        concepts_prefetch, base_vocab_prefetch = _get_prefetch_for_vocabularies()
        v = VocabularyModel.objects.prefetch_related(
            concepts_prefetch,
            base_vocab_prefetch,
        ).get(name=name)
    except VocabularyModel.DoesNotExist:
        raise VocabularyNotFoundError(Vocabulary, query_name="name", query_value=name)

    return as_domain_object(v)


def newest_base_vocabulary_by_name(name: str) -> Vocabulary:
    concepts_prefetch, _ = _get_prefetch_for_vocabularies()
    vocabularies_by_name = VocabularyModel.objects.filter(name=name, is_limited=False)
    vocabularies_by_name = vocabularies_by_name.prefetch_related(concepts_prefetch).order_by(
        "-version"
    )

    v = vocabularies_by_name.first()
    if not v:
        raise VocabularyNotFoundError(Vocabulary, query_name="name", query_value=name)

    return cast(Vocabulary, as_domain_object(v))


def find_limited_by_base_vocabulary(base_vocabulary_id: VocabularyId) -> list[LimitedVocabulary]:
    concepts_prefetch, base_vocab_prefetch = _get_prefetch_for_vocabularies()
    return [
        cast(LimitedVocabulary, as_domain_object(v))
        for v in VocabularyModel.objects.prefetch_related(
            concepts_prefetch,
            base_vocab_prefetch,
        ).filter(base_vocabulary_id=base_vocabulary_id)
    ]


def all() -> Sequence[VocabularyProtocol]:
    concepts_prefetch, base_vocab_prefetch = _get_prefetch_for_vocabularies()
    queryset = VocabularyModel.objects.prefetch_related(
        concepts_prefetch,
        base_vocab_prefetch,
    )
    return DomainQuerySet(queryset, as_domain_object)


def all_limited() -> list[LimitedVocabulary]:
    concepts_prefetch, base_vocab_prefetch = _get_prefetch_for_vocabularies()
    return [
        cast(LimitedVocabulary, as_domain_object(v))
        for v in VocabularyModel.objects.prefetch_related(
            concepts_prefetch,
            base_vocab_prefetch,
        ).filter(is_limited=True)
    ]


def save(vocabulary: VocabularyProtocol) -> None:
    if vocabulary.id is None:
        # Create new vocabulary
        if isinstance(vocabulary, LimitedVocabulary):
            v = VocabularyModel.objects.create(
                name=vocabulary.name,
                version=vocabulary.version,
                is_limited=True,
                base_vocabulary_id=vocabulary.base_vocabulary.id,
            )
            # Update the domain object with the assigned ID
            vocabulary.id = VocabularyId(v.pk)
        else:
            v = VocabularyModel.objects.create(
                name=vocabulary.name,
                version=vocabulary.version,
            )
            # Update the domain object with the assigned ID
            vocabulary.id = VocabularyId(v.pk)
    else:
        # Update existing vocabulary
        v, _ = VocabularyModel.objects.get_or_create(pk=vocabulary.id)
        v.name = vocabulary.name
        v.version = vocabulary.version
        if isinstance(vocabulary, LimitedVocabulary):
            v.is_limited = True
            v.base_vocabulary_id = vocabulary.base_vocabulary.id

    concepts: Collection[VocabularyConcept]
    if isinstance(vocabulary, Vocabulary):
        concepts = vocabulary.concepts
    elif isinstance(vocabulary, LimitedVocabulary):
        concepts = vocabulary.disallowed_concepts
        # Clear existing concepts for limited vocabularies (they store disallowed concepts)
        v.concepts.all().delete()
    else:
        raise ValueError(f"Unsupported vocabulary type: {type(vocabulary)}")

    # First pass: create all concepts without parent relationships
    for c in concepts:
        mc, _ = v.concepts.get_or_create(entity_id=c.id)
        mc.concept_id = c.concept_id
        mc.name = c.name
        mc.hint = c.description
        mc.save()

    # Second pass: set parent relationships
    for c in concepts:
        if c.parent is not None:
            try:
                mc = v.concepts.get(entity_id=c.id)
                parent_concept = v.concepts.get(entity_id=c.parent)
                mc.parent = parent_concept
                mc.save()
            except v.concepts.model.DoesNotExist:
                # Parent concept doesn't exist, skip
                pass

    v.save()


def delete(vocabulary: VocabularyProtocol) -> None:
    id = vocabulary.id
    if id is None:
        raise ValueError("Cannot delete vocabulary without an ID")

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
        base_vocabulary_model = cast(VocabularyModel, v.base_vocabulary)
        base_vocabulary_domain = Vocabulary(
            id=VocabularyId(base_vocabulary_model.pk),
            name=base_vocabulary_model.name,
            version=base_vocabulary_model.version,
            concepts=[
                VocabularyConcept(
                    id=ConceptId(str(c.entity_id)),
                    concept_id=c.concept_id,
                    vocabulary=VocabularyId(base_vocabulary_model.pk),
                    name=c.name,
                    description=c.hint,
                    parent=ConceptId(str(c.parent.entity_id)) if c.parent else None,
                )
                for c in base_vocabulary_model.concepts.all()
            ],
        )

        vocabulary = LimitedVocabulary(
            id=VocabularyId(v.pk),
            base_vocabulary=base_vocabulary_domain,
            name=v.name,
            version=base_vocabulary_model.version,
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

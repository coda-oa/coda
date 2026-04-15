from collections.abc import Collection, Sequence
from typing import Any, cast

from django.db.models import Prefetch, QuerySet, Model

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


# Maximum depth for nested limited vocabularies (e.g., Base -> L1 -> L2 -> ... -> Ln)
# Increase this if you need to support deeper nesting
MAX_VOCABULARY_NESTING_DEPTH = 10


def _build_recursive_base_vocab_prefetch(
    depth: int,
) -> Prefetch[str, QuerySet[Model, Model], str] | None:
    """Recursively build prefetch for nested base vocabularies.

    Args:
        depth: How many levels deep to prefetch (0 = no prefetch)

    Returns:
        Prefetch object for base_vocabulary, or None if depth is 0
    """
    if depth <= 0:
        return None

    concepts_prefetch = Prefetch(
        "concepts",
        queryset=ConceptModel.objects.select_related("parent"),
    )

    # Recursively build the next level
    nested_prefetch = _build_recursive_base_vocab_prefetch(depth - 1)

    # Build prefetch list for this level
    prefetch_list: list[Prefetch[str, QuerySet[Model, Model], str]] = [concepts_prefetch]
    if nested_prefetch:
        prefetch_list.append(nested_prefetch)

    return Prefetch(
        "base_vocabulary",
        queryset=VocabularyModel.objects.prefetch_related(*prefetch_list),
    )


def prefetches_for(
    prefix: str | None = None,
) -> list[Prefetch[str, QuerySet[Model, Model], str]]:
    """Return Prefetch objects to fully hydrate a VocabularyModel at the given
    ORM traversal prefix.

    Covers:
    - {prefix}__concepts (with parent select_related)
    - {prefix}__base_vocabulary (recursive chain up to MAX_VOCABULARY_NESTING_DEPTH,
      each level including its own concepts)

    Args:
        prefix: ORM traversal path to the VocabularyModel, e.g.
                "publication_type__vocabulary". None means the queryset is
                already scoped to VocabularyModel rows.

    Examples:
        # Standalone vocabulary queryset:
        VocabularyModel.objects.prefetch_related(*prefetches_for())

        # Nested inside a publication queryset:
        PublicationModel.objects.prefetch_related(
            *prefetches_for("publication_type__vocabulary")
        )
    """

    def path(field: str) -> str:
        return f"{prefix}__{field}" if prefix else field

    concepts_prefetch = Prefetch(
        path("concepts"),
        queryset=ConceptModel.objects.select_related("parent"),
    )

    nested = _build_recursive_base_vocab_prefetch(MAX_VOCABULARY_NESTING_DEPTH)
    if nested is not None:
        base_vocab_prefetch: Prefetch[str, QuerySet[Model, Model], str] | None = Prefetch(
            path("base_vocabulary"),
            queryset=nested.queryset,
        )
    else:
        base_vocab_prefetch = None

    return [p for p in [concepts_prefetch, base_vocab_prefetch] if p is not None]


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
        v = VocabularyModel.objects.prefetch_related(*prefetches_for()).get(pk=id)
    except VocabularyModel.DoesNotExist:
        raise VocabularyNotFoundError(Vocabulary, query_name="id", query_value=id)

    vocabulary = as_domain_object(v)

    return vocabulary


def get_limited_by_id(id: VocabularyId) -> LimitedVocabulary:
    v = get_by_id(id)
    if not isinstance(v, LimitedVocabulary):
        raise VocabularyNotFoundError(LimitedVocabulary, query_name="id", query_value=id)

    return v


def get_by_name(name: str) -> VocabularyProtocol:
    """Return the single vocabulary matching *name*.

    Raises:
        VocabularyNotFoundError: if no vocabulary with that name exists.
        django.core.exceptions.MultipleObjectsReturned: if more than one
            vocabulary shares the name (there is no DB unique constraint on
            name — adding one is tracked as a follow-up task).
    """
    try:
        v = VocabularyModel.objects.prefetch_related(*prefetches_for()).get(name=name)
    except VocabularyModel.DoesNotExist:
        raise VocabularyNotFoundError(Vocabulary, query_name="name", query_value=name)

    return as_domain_object(v)


def newest_base_vocabulary_by_name(name: str) -> Vocabulary:
    vocabularies_by_name = VocabularyModel.objects.filter(name=name, is_limited=False)
    vocabularies_by_name = vocabularies_by_name.prefetch_related(*prefetches_for()).order_by(
        "-version"
    )

    v = vocabularies_by_name.first()
    if not v:
        raise VocabularyNotFoundError(Vocabulary, query_name="name", query_value=name)

    return cast(Vocabulary, as_domain_object(v))


def find_limited_by_base_vocabulary(base_vocabulary_id: VocabularyId) -> list[LimitedVocabulary]:
    return [
        cast(LimitedVocabulary, as_domain_object(v))
        for v in VocabularyModel.objects.prefetch_related(*prefetches_for()).filter(
            base_vocabulary_id=base_vocabulary_id
        )
    ]


def all() -> Sequence[VocabularyProtocol]:
    queryset = VocabularyModel.objects.prefetch_related(*prefetches_for())
    return DomainQuerySet(queryset, as_domain_object)


def all_limited() -> list[LimitedVocabulary]:
    return [
        cast(LimitedVocabulary, as_domain_object(v))
        for v in VocabularyModel.objects.prefetch_related(*prefetches_for()).filter(is_limited=True)
    ]


def _create_or_update_vocabulary_model(vocabulary: VocabularyProtocol) -> VocabularyModel:
    if vocabulary.id is None:
        # Create new vocabulary
        if isinstance(vocabulary, LimitedVocabulary):
            v = VocabularyModel.objects.create(
                name=vocabulary.name,
                version=vocabulary.version,
                is_limited=True,
                base_vocabulary_id=vocabulary.base_vocabulary.id,
            )
            vocabulary.id = VocabularyId(v.pk)
        else:
            v = VocabularyModel.objects.create(
                name=vocabulary.name,
                version=vocabulary.version,
            )
            vocabulary.id = VocabularyId(v.pk)
    else:
        # Update existing vocabulary
        v, _ = VocabularyModel.objects.get_or_create(pk=vocabulary.id)
        v.name = vocabulary.name
        v.version = vocabulary.version
        if isinstance(vocabulary, LimitedVocabulary):
            v.is_limited = True
            v.base_vocabulary_id = vocabulary.base_vocabulary.id

    return v


def _get_concepts_for_save(
    vocabulary: VocabularyProtocol, vocabulary_model: VocabularyModel
) -> Collection[VocabularyConcept]:
    if isinstance(vocabulary, Vocabulary):
        return vocabulary.concepts
    elif isinstance(vocabulary, LimitedVocabulary):
        # Clear existing concepts for limited vocabularies (they store disallowed concepts)
        vocabulary_model.concepts.all().delete()
        return vocabulary.disallowed_concepts
    else:
        raise ValueError(f"Unsupported vocabulary type: {type(vocabulary)}")


def _prepare_concepts_for_bulk_save(
    concepts: Collection[VocabularyConcept],
    existing_concepts: dict[str, ConceptModel],
    vocabulary_model: VocabularyModel,
) -> tuple[list[ConceptModel], list[ConceptModel]]:
    """Categorize concepts into create and update lists without parent relationships."""
    concepts_to_create = []
    concepts_to_update = []

    for c in concepts:
        entity_id_str = str(c.id)
        if entity_id_str in existing_concepts:
            # Update existing concept
            mc = existing_concepts[entity_id_str]
            mc.concept_id = c.concept_id
            mc.name = c.name
            mc.hint = c.description
            mc.parent = None  # Clear parent, will be set in second pass
            concepts_to_update.append(mc)
        else:
            # Create new concept
            mc = ConceptModel(
                vocabulary=vocabulary_model,
                entity_id=c.id,
                concept_id=c.concept_id,
                name=c.name,
                hint=c.description,
            )
            concepts_to_create.append(mc)
            existing_concepts[entity_id_str] = mc

    return concepts_to_create, concepts_to_update


def _perform_bulk_operations(
    vocabulary_model: VocabularyModel,
    concepts_to_create: list[ConceptModel],
    concepts_to_update: list[ConceptModel],
    existing_concepts: dict[str, ConceptModel],
) -> dict[str, ConceptModel]:
    """Execute bulk create/update operations and return refreshed concept lookup."""
    if concepts_to_create:
        ConceptModel.objects.bulk_create(concepts_to_create)
    if concepts_to_update:
        ConceptModel.objects.bulk_update(
            concepts_to_update, fields=["concept_id", "name", "hint", "parent"]
        )

    # Refresh the lookup dict only if we created new concepts (to get their IDs)
    if concepts_to_create:
        return {str(c.entity_id): c for c in vocabulary_model.concepts.all()}

    return existing_concepts


def _update_parent_relationships(
    concepts: Collection[VocabularyConcept],
    existing_concepts: dict[str, ConceptModel],
) -> None:
    """Set parent relationships for concepts in bulk."""
    concepts_with_parents = []

    for c in concepts:
        if c.parent is not None:
            entity_id_str = str(c.id)
            parent_id_str = str(c.parent)
            if entity_id_str in existing_concepts and parent_id_str in existing_concepts:
                mc = existing_concepts[entity_id_str]
                mc.parent = existing_concepts[parent_id_str]
                concepts_with_parents.append(mc)

    if concepts_with_parents:
        ConceptModel.objects.bulk_update(concepts_with_parents, fields=["parent"])


def _save_concepts(
    vocabulary_model: VocabularyModel, concepts: Collection[VocabularyConcept]
) -> None:
    existing_concepts = {str(c.entity_id): c for c in vocabulary_model.concepts.all()}

    concepts_to_create, concepts_to_update = _prepare_concepts_for_bulk_save(
        concepts, existing_concepts, vocabulary_model
    )

    existing_concepts = _perform_bulk_operations(
        vocabulary_model, concepts_to_create, concepts_to_update, existing_concepts
    )

    _update_parent_relationships(concepts, existing_concepts)


def save(vocabulary: VocabularyProtocol) -> None:
    v = _create_or_update_vocabulary_model(vocabulary)
    concepts = _get_concepts_for_save(vocabulary, v)
    _save_concepts(v, concepts)
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

        base_vocabulary_domain = as_domain_object(base_vocabulary_model)

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

from dataclasses import field
from typing import NamedTuple

from coda.apps.publications.models import PublicationAttachedConcept
from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.apps.publications.services import concept_tree
from coda.domain.vocabulary import (
    LimitedVocabulary,
    UnknownConcept,
    VocabularyId,
    VocabularyProtocol,
)


def build_concept_trees(
    vocabulary: LimitedVocabulary,
) -> tuple[list[concept_tree.ConceptTreeNode], list[concept_tree.ConceptTreeNode]]:
    return concept_tree.build(vocabulary)


def create_limited_from(vocabulary_id: VocabularyId, name: str) -> VocabularyId:
    vocabulary = vocabulary_repository.create_limited(base_vocabulary_id=vocabulary_id, name=name)
    assert vocabulary.id is not None  # Repository create_limited always assigns an ID
    return vocabulary.id


def disallow_concept(vocabulary_id: VocabularyId, concept_id: str) -> None:
    limited = vocabulary_repository.get_limited_by_id(vocabulary_id)
    limited.disallow(concept_id)
    vocabulary_repository.save(limited)


def allow_concept(vocabulary_id: VocabularyId, concept_id: str) -> None:
    limited = vocabulary_repository.get_limited_by_id(vocabulary_id)
    limited.allow(concept_id)
    vocabulary_repository.save(limited)


def delete(vocabulary_id: VocabularyId) -> None:
    vocabulary = vocabulary_repository.get_by_id(vocabulary_id)
    if isinstance(vocabulary, LimitedVocabulary):
        publication_count = publication_repository.count_publications_by_vocabulary(vocabulary_id)
        _migrate_publications_to_base_vocabulary(vocabulary, publication_count)

    vocabulary_repository.delete(vocabulary)


class VocabularyUsage(NamedTuple):
    vocabulary: VocabularyProtocol
    publication_count: int = 0
    derived_vocabularies: list[LimitedVocabulary] = field(default_factory=list)

    def is_used(self) -> bool:
        return bool(self.publication_count or self.derived_vocabularies)

    def can_be_deleted(self) -> bool:
        if self.derived_vocabularies:
            return False

        if isinstance(self.vocabulary, LimitedVocabulary):
            return True

        return not self.publication_count


def get_usage(vocabulary_id: VocabularyId) -> "VocabularyUsage":
    return VocabularyUsage(
        vocabulary=vocabulary_repository.get_by_id(vocabulary_id),
        publication_count=publication_repository.count_publications_by_vocabulary(vocabulary_id),
        derived_vocabularies=vocabulary_repository.find_limited_by_base_vocabulary(vocabulary_id),
    )


def _migrate_publications_to_base_vocabulary(
    vocabulary: LimitedVocabulary, publication_count: int
) -> None:
    """Re-point publications from the limited vocabulary to its base vocabulary.

    Limited vocabularies store no Concept rows of their own — their concepts
    are projections of the base vocabulary's concepts. Publications reference
    the limited vocabulary only via the attached-concept row's vocabulary FK,
    so migrating is a bulk UPDATE of those rows: the base concept with the
    same entity_id takes over (entity_id already matches); a concept missing
    from the base becomes the unknown concept.
    """
    if not publication_count:
        return

    base = vocabulary.base_vocabulary
    assert base.id is not None  # base vocabulary is always persisted
    limited_id = vocabulary.id
    assert limited_id is not None  # limited vocabulary is persisted before deletion

    base_entity_ids = [str(c.id) for c in base.concepts]
    rows = PublicationAttachedConcept.objects.filter(vocabulary_id=limited_id)
    known = rows.filter(entity_id__in=base_entity_ids)
    unknown = rows.exclude(entity_id__in=base_entity_ids)

    known.update(vocabulary_id=base.id)
    unknown.update(
        vocabulary_id=base.id,
        entity_id=UnknownConcept.id,
        name="unknown",
    )

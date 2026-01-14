from typing import NamedTuple

from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.apps.publications.services import concept_tree
from coda.domain.publication import BasePublication
from coda.domain.vocabulary import (
    LimitedVocabulary,
    VocabularyConcept,
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
        publications = publication_repository.find_publications_by_vocabulary(vocabulary_id)
        _migrate_publications_to_base_vocabulary(vocabulary, publications)

    vocabulary_repository.delete(vocabulary)


def get_usage(vocabulary_id: VocabularyId) -> "VocabularyUsage":
    return VocabularyUsage(
        vocabulary=vocabulary_repository.get_by_id(vocabulary_id),
        publications=publication_repository.find_publications_by_vocabulary(vocabulary_id),
        derived_vocabularies=vocabulary_repository.find_limited_by_base_vocabulary(vocabulary_id),
    )


def _migrate_publications_to_base_vocabulary(
    vocabulary: LimitedVocabulary, publications: list[BasePublication]
) -> None:
    for publication in publications:
        publication.publication_type = _migrate_matching_concept_to_base_vocabulary(
            publication.publication_type,
            vocabulary,
        )

        publication.subject_area = _migrate_matching_concept_to_base_vocabulary(
            publication.subject_area,
            vocabulary,
        )

        publication_repository.update(publication)


def _migrate_matching_concept_to_base_vocabulary(
    concept: VocabularyConcept, vocabulary: LimitedVocabulary
) -> VocabularyConcept:
    if concept.vocabulary == vocabulary.id:
        return vocabulary.get_base_concept(concept.concept_id)

    return concept


class VocabularyUsage(NamedTuple):
    vocabulary: VocabularyProtocol
    publications: list[BasePublication] = []
    derived_vocabularies: list[LimitedVocabulary] = []

    def is_used(self) -> bool:
        return bool(self.publications or self.derived_vocabularies)

    def can_be_deleted(self) -> bool:
        if self.derived_vocabularies:
            return False

        if isinstance(self.vocabulary, LimitedVocabulary):
            return True

        return not self.publications

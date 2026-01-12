from typing import NamedTuple
from dataclasses import dataclass

from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.domain.publication import BasePublication
from coda.domain.vocabulary import (
    LimitedVocabulary,
    VocabularyConcept,
    VocabularyId,
    VocabularyProtocol,
)


@dataclass
class ConceptTreeNode:
    """A node in a concept tree with hierarchical structure."""

    concept: VocabularyConcept
    children: list["ConceptTreeNode"]


class ConceptTreeBuilder:
    def __init__(self, vocabulary: LimitedVocabulary) -> None:
        self.vocabulary = vocabulary
        self.roots, self.children_map = vocabulary.get_concept_hierarchy()
        self.allowed_concept_ids = {
            c.concept_id
            for c in vocabulary.base_vocabulary.concepts
            if vocabulary.is_concept_allowed(c.concept_id)
        }

    def build(self) -> tuple[list[ConceptTreeNode], list[ConceptTreeNode]]:
        allowed_tree = []
        forbidden_tree = []

        for root in self.roots:
            node = self._build_tree(root, True)
            if node:
                allowed_tree.append(node)
            node = self._build_tree(root, False)
            if node:
                forbidden_tree.append(node)

        return allowed_tree, forbidden_tree

    def _has_relevant_descendants(self, concept: VocabularyConcept, for_allowed_tree: bool) -> bool:
        is_allowed = concept.concept_id in self.allowed_concept_ids
        target_status = for_allowed_tree
        if is_allowed == target_status:
            return True
        for child in self.children_map.get(concept.id, []):
            if self._has_relevant_descendants(child, for_allowed_tree):
                return True
        return False

    def _build_tree(
        self, concept: VocabularyConcept, for_allowed_tree: bool
    ) -> ConceptTreeNode | None:
        if not self._has_relevant_descendants(concept, for_allowed_tree):
            return None

        children = []
        for child in self.children_map.get(concept.id, []):
            child_node = self._build_tree(child, for_allowed_tree)
            if child_node:
                children.append(child_node)

        # Move concept to the limited vocabulary context
        moved_concept = self.vocabulary._move_concept_to_self(concept)

        return ConceptTreeNode(
            concept=moved_concept,
            children=children,
        )


def build_concept_trees(
    vocabulary: LimitedVocabulary,
) -> tuple[list[ConceptTreeNode], list[ConceptTreeNode]]:
    builder = ConceptTreeBuilder(vocabulary)
    return builder.build()


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

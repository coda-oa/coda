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


def build_concept_trees(
    vocabulary: LimitedVocabulary,
) -> tuple[list[ConceptTreeNode], list[ConceptTreeNode]]:
    """Build allowed and forbidden concept trees from a limited vocabulary.

    This service function handles the tree building logic, separating it from
    the domain concerns of concept relationships.

    Returns:
        A tuple of (allowed_tree, forbidden_tree) where each tree contains
        only concepts relevant to that tree (allowed or forbidden).
    """
    # Get hierarchy from domain
    roots, children_map = vocabulary.get_concept_hierarchy()

    all_concepts = list(vocabulary.base_vocabulary.concepts)
    allowed_concept_ids = {
        c.concept_id for c in all_concepts if vocabulary.is_concept_allowed(c.concept_id)
    }

    def has_relevant_descendants(concept: VocabularyConcept, for_allowed_tree: bool) -> bool:
        """Check if a concept or its descendants are relevant for the tree type."""
        is_allowed = concept.concept_id in allowed_concept_ids
        target_status = for_allowed_tree
        if is_allowed == target_status:
            return True
        for child in children_map.get(concept.id, []):
            if has_relevant_descendants(child, for_allowed_tree):
                return True
        return False

    def build_tree(concept: VocabularyConcept, for_allowed_tree: bool) -> ConceptTreeNode | None:
        """Recursively build a tree node if it's relevant for the tree type."""
        if not has_relevant_descendants(concept, for_allowed_tree):
            return None

        children = []
        for child in children_map.get(concept.id, []):
            child_node = build_tree(child, for_allowed_tree)
            if child_node:
                children.append(child_node)

        # Move concept to the limited vocabulary context
        moved_concept = vocabulary._move_concept_to_self(concept)

        return ConceptTreeNode(
            concept=moved_concept,
            children=children,
        )

    allowed_tree = []
    forbidden_tree = []

    for root in roots:
        node = build_tree(root, True)
        if node:
            allowed_tree.append(node)
        node = build_tree(root, False)
        if node:
            forbidden_tree.append(node)

    return allowed_tree, forbidden_tree


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

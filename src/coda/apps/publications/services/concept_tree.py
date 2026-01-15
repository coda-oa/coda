from dataclasses import dataclass
from collections import defaultdict

from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    VocabularyConcept,
    VocabularyProtocol,
)


@dataclass
class ConceptTreeNode:
    concept: VocabularyConcept
    children: list["ConceptTreeNode"]


def build(vocabulary: LimitedVocabulary) -> tuple[list[ConceptTreeNode], list[ConceptTreeNode]]:
    # Use root base vocabulary to preserve full hierarchical structure
    root_base_vocab = vocabulary.get_root_base_vocabulary()
    roots, children_map = _get_hierarchy_from_vocab(root_base_vocab, vocabulary)

    # Determine which concepts are available in the current vocabulary
    allowed_concept_ids = {
        c.concept_id
        for c in vocabulary.base_vocabulary.concepts
        if vocabulary.is_concept_allowed(c.concept_id)
    }

    allowed_tree = []
    forbidden_tree = []

    for root in roots:
        node = _build_tree(root, children_map, allowed_concept_ids, True)
        if node:
            allowed_tree.append(node)
        node = _build_tree(root, children_map, allowed_concept_ids, False)
        if node:
            forbidden_tree.append(node)

    return allowed_tree, forbidden_tree


def _get_hierarchy_from_vocab(
    source_vocab: VocabularyProtocol,
    target_vocab: LimitedVocabulary,
) -> tuple[list[VocabularyConcept], dict[ConceptId, list[VocabularyConcept]]]:
    """Get concept hierarchy from source vocabulary with target vocabulary IDs."""
    all_concepts = [target_vocab._move_concept_to_self(c) for c in source_vocab.concepts]
    children_map: dict[ConceptId, list[VocabularyConcept]] = defaultdict(list)
    roots = []

    for concept in all_concepts:
        if concept.parent is None:
            roots.append(concept)
        else:
            children_map[concept.parent].append(concept)

    return roots, dict(children_map)


def _has_relevant_descendants(
    concept: VocabularyConcept,
    children_map: dict[ConceptId, list[VocabularyConcept]],
    allowed_concept_ids: set[str],
    for_allowed_tree: bool,
) -> bool:
    is_allowed = concept.concept_id in allowed_concept_ids
    target_status = for_allowed_tree
    if is_allowed == target_status:
        return True
    for child in children_map.get(concept.id, []):
        if _has_relevant_descendants(child, children_map, allowed_concept_ids, for_allowed_tree):
            return True
    return False


def _build_tree(
    concept: VocabularyConcept,
    children_map: dict[ConceptId, list[VocabularyConcept]],
    allowed_concept_ids: set[str],
    for_allowed_tree: bool,
) -> ConceptTreeNode | None:
    if not _has_relevant_descendants(concept, children_map, allowed_concept_ids, for_allowed_tree):
        return None

    children = []
    for child in children_map.get(concept.id, []):
        child_node = _build_tree(child, children_map, allowed_concept_ids, for_allowed_tree)
        if child_node:
            children.append(child_node)

    return ConceptTreeNode(
        concept=concept,
        children=children,
    )

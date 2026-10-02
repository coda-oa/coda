from dataclasses import dataclass

from django import template

from coda.apps.publications.services import concept_tree
from coda.domain.vocabulary import LimitedVocabulary, VocabularyConcept

register = template.Library()


@dataclass
class UITreeNode:
    concept: VocabularyConcept
    children: list["UITreeNode"]
    is_allowed: bool  # For template: whether to show checkbox or just label
    zebra_index: int  # For template: sequential index for zebra striping
    level: int  # For template: hierarchy level (1=root, 2=children, etc.)


@dataclass(frozen=True)
class AnnotatedTree:
    nodes: list[UITreeNode]
    levels: set[int]  # hierarchy levels that contain at least one checkbox

    @property
    def level_range(self) -> list[int]:
        return sorted(self.levels)


def _annotate_node(
    node: concept_tree.ConceptTreeNode,
    vocabulary: LimitedVocabulary,
    allowed_side: bool,
    level: int,
    zebra_counter: list[int],
    levels: set[int],
) -> UITreeNode:
    zebra_counter[0] += 1
    current_index = zebra_counter[0]

    concept_id = node.concept.concept_id
    show_checkbox = False
    if vocabulary.base_vocabulary.has_concept(concept_id):
        is_concept_allowed = vocabulary.is_concept_allowed(concept_id)
        show_checkbox = is_concept_allowed if allowed_side else not is_concept_allowed

    if show_checkbox:
        levels.add(level)

    return UITreeNode(
        concept=node.concept,
        children=[
            _annotate_node(child, vocabulary, allowed_side, level + 1, zebra_counter, levels)
            for child in node.children
        ],
        is_allowed=show_checkbox,
        zebra_index=current_index,
        level=level,
    )


def concept_ui_tree(
    tree: list[concept_tree.ConceptTreeNode], vocabulary: LimitedVocabulary, allowed_side: bool
) -> AnnotatedTree:
    """Annotate a concept tree for rendering: checkbox visibility, striping, levels."""
    zebra_counter = [0]
    levels: set[int] = set()
    nodes = [
        _annotate_node(node, vocabulary, allowed_side, 1, zebra_counter, levels)
        for node in tree
    ]
    return AnnotatedTree(nodes=nodes, levels=levels)


@register.simple_tag
def vocabulary_ui_tree(
    tree: list[concept_tree.ConceptTreeNode], vocabulary: LimitedVocabulary, side: str
) -> AnnotatedTree:
    """Template-side entry point: ``{% vocabulary_ui_tree allowed_tree vocabulary "allowed" as ui %}``."""
    return concept_ui_tree(tree, vocabulary, side == "allowed")

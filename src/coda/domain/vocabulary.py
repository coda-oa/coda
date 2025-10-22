import uuid
from collections.abc import Collection
from dataclasses import dataclass
from typing import NewType, Protocol

from coda.domain.errors import DomainError


class ConceptId(uuid.UUID):
    @classmethod
    def new(cls) -> "ConceptId":
        return cls(str(uuid.uuid4()))


VocabularyId = NewType("VocabularyId", int)


class VocabularyProtocol(Protocol):
    id: VocabularyId | None
    name: str
    version: str

    def has_concept(self, concept_id: str) -> bool:
        """Check if a concept exists in the vocabulary"""
        ...

    def get_concept(self, concept_id: str) -> "VocabularyConcept":
        """Get a concept by its concept ID unique to the vocabulary"""
        ...

    def get_concept_by_id(self, id: ConceptId) -> "VocabularyConcept":
        """Get a concept by its globally unique ID"""
        ...

    @property
    def concepts(self) -> Collection["VocabularyConcept"]:
        """Get all concepts in the vocabulary"""
        ...


class DuplicateConceptError(DomainError):
    def __init__(self, vocabulary: VocabularyProtocol, concept_id: str, *args: object) -> None:
        super().__init__(
            f"Concept ID {concept_id} already exists in vocabulary {vocabulary.name} ({vocabulary.version})",
            *args,
        )
        self.concept_id = concept_id


class ConceptNotFoundError(DomainError):
    def __init__(self, vocabulary: VocabularyProtocol, concept_id: str, *args: object) -> None:
        super().__init__(
            f"Concept {concept_id} was not found in vocabulary {vocabulary.name} ({vocabulary.version})",
            *args,
        )


class ConceptNotAllowedError(DomainError):
    def __init__(self, vocabulary: "LimitedVocabulary", concept_id: str, *args: object) -> None:
        super().__init__(
            f"Concept {concept_id} is not allowed in vocabulary {vocabulary.name} ({vocabulary.version})",
            *args,
        )


@dataclass(frozen=True)
class VocabularyConcept:
    id: ConceptId
    concept_id: str
    vocabulary: VocabularyId
    name: str = ""
    description: str = ""
    parent: ConceptId | None = None

    @classmethod
    def new(
        cls,
        concept_id: str,
        vocabulary: VocabularyId,
        name: str = "",
        description: str = "",
    ) -> "VocabularyConcept":
        return VocabularyConcept(ConceptId.new(), concept_id, vocabulary, name, description)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VocabularyConcept):
            return NotImplemented

        return self.id == other.id


@dataclass(repr=True)
class Vocabulary:
    def __init__(
        self,
        id: VocabularyId | None,
        name: str,
        version: str,
        concepts: Collection["VocabularyConcept"] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.version = version
        self._concepts: list[VocabularyConcept] = list(concepts or [])

    def get_concept_by_id(self, id: ConceptId) -> VocabularyConcept:
        for concept in self._concepts:
            if concept.id == id:
                return concept

        raise ConceptNotFoundError(self, str(id))

    def has_concept(self, concept_id: str) -> bool:
        return any(c.concept_id == concept_id for c in self._concepts)

    def get_concept(self, concept_id: str) -> VocabularyConcept:
        index = self._find_concept_index(concept_id)
        return self._concepts[index]

    @property
    def concepts(self) -> Collection[VocabularyConcept]:
        return tuple(self._concepts)

    def add_concept(self, concept_id: str, name: str = "", description: str = "") -> None:
        if any(c.concept_id == concept_id for c in self._concepts):
            raise DuplicateConceptError(self, concept_id=concept_id)

        # Use placeholder ID for unsaved vocabularies
        vocab_id = self.id if self.id is not None else VocabularyId(-1)
        concept = VocabularyConcept.new(
            concept_id=concept_id, name=name, description=description, vocabulary=vocab_id
        )
        self._concepts.append(concept)

    def _find_concept_index(self, concept_id: str) -> int:
        for i, concept in enumerate(self._concepts):
            if concept.concept_id == concept_id:
                return i

        raise ConceptNotFoundError(self, concept_id)


_UnknownConceptId = ConceptId("fd0febd8-2218-4327-a517-d78b7f8f58ff")
UnknownConcept = VocabularyConcept(
    _UnknownConceptId, "unknown", VocabularyId(0), "Unknown", "Unknown"
)


@dataclass
class TreeNode:
    concept: VocabularyConcept
    children: list["TreeNode"]
    is_allowed: bool


@dataclass
class LimitedVocabulary:
    id: VocabularyId | None
    base_vocabulary: VocabularyProtocol
    name: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        self._disallowed: set[str] = set()

    def has_concept(self, concept_id: str) -> bool:
        return concept_id not in self._disallowed and self.base_vocabulary.has_concept(concept_id)

    @property
    def concepts(self) -> Collection[VocabularyConcept]:
        return [
            self._move_concept_to_self(c)
            for c in self.base_vocabulary.concepts
            if c.concept_id not in self._disallowed
        ]

    def _move_concept_to_self(self, c: VocabularyConcept) -> VocabularyConcept:
        return VocabularyConcept(
            id=c.id,
            concept_id=c.concept_id,
            vocabulary=self.id or VocabularyId(-1),
            name=c.name,
            description=c.description,
            parent=c.parent,
        )

    @property
    def disallowed_concepts(self) -> Collection[VocabularyConcept]:
        return [
            self._move_concept_to_self(c)
            for c in self.base_vocabulary.concepts
            if c.concept_id in self._disallowed
        ]

    def get_concept_by_id(self, id: ConceptId) -> VocabularyConcept:
        if id in self._disallowed:
            raise ConceptNotAllowedError(self, str(id))

        return self._move_concept_to_self(self.base_vocabulary.get_concept_by_id(id))

    def get_base_concept(self, concept_id: str) -> VocabularyConcept:
        """Get a concept from the base vocabulary by its concept ID"""
        return self.base_vocabulary.get_concept(concept_id)

    def get_concept(self, concept_id: str) -> VocabularyConcept:
        if concept_id in self._disallowed:
            raise ConceptNotAllowedError(self, concept_id)

        return self._move_concept_to_self(self.base_vocabulary.get_concept(concept_id))

    def disallow(self, concept_id: str) -> None:
        self._disallowed.add(concept_id)

    def allow(self, concept_id: str) -> None:
        self._disallowed.discard(concept_id)

    def clear_disallowed(self) -> None:
        """Clear all disallowed concepts."""
        self._disallowed.clear()

    def disallowed_concepts_ids(self) -> set[str]:
        """Get the set of disallowed concept IDs."""
        return self._disallowed.copy()

    def get_any_concept(self, concept_id: str) -> VocabularyConcept:
        return self._move_concept_to_self(self.base_vocabulary.get_concept(concept_id))

    def get_concept_trees(self) -> tuple[list[TreeNode], list[TreeNode]]:
        from collections import defaultdict

        all_concepts = list(self.base_vocabulary.concepts)
        allowed_concept_ids = {
            c.concept_id for c in all_concepts if c.concept_id not in self._disallowed
        }

        # Build parent-to-children mapping
        children_map: dict[ConceptId, list[VocabularyConcept]] = defaultdict(list)
        roots = []
        for concept in all_concepts:
            if concept.parent is None:
                roots.append(concept)
            else:
                children_map[concept.parent].append(concept)

        def has_relevant_descendants(concept: VocabularyConcept, for_allowed_tree: bool) -> bool:
            is_allowed = concept.concept_id in allowed_concept_ids
            target_status = for_allowed_tree
            if is_allowed == target_status:
                return True
            for child in children_map.get(concept.id, []):
                if has_relevant_descendants(child, for_allowed_tree):
                    return True
            return False

        def build_tree(concept: VocabularyConcept, for_allowed_tree: bool) -> TreeNode | None:
            if not has_relevant_descendants(concept, for_allowed_tree):
                return None
            children = []
            for child in children_map.get(concept.id, []):
                child_node = build_tree(child, for_allowed_tree)
                if child_node:
                    children.append(child_node)
            is_allowed = concept.concept_id in allowed_concept_ids

            # For templates: show checkbox if this concept belongs to this tree's purpose
            # Allowed tree: show checkbox for allowed concepts
            # Forbidden tree: show checkbox for forbidden concepts
            show_checkbox = is_allowed if for_allowed_tree else not is_allowed

            return TreeNode(
                concept=self._move_concept_to_self(concept),
                children=children,
                is_allowed=show_checkbox,
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

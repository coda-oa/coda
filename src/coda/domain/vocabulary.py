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
    id: VocabularyId
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
        id: VocabularyId,
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

        concept = VocabularyConcept.new(
            concept_id=concept_id, name=name, description=description, vocabulary=self.id
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
class LimitedVocabulary:
    id: VocabularyId
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
            vocabulary=self.id,
            name=c.name,
            description=c.description,
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

    def get_any_concept(self, concept_id: str) -> VocabularyConcept:
        return self._move_concept_to_self(self.base_vocabulary.get_concept(concept_id))

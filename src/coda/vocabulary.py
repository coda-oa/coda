from collections.abc import Collection
from dataclasses import dataclass
from typing import NewType, Protocol

ConceptId = NewType("ConceptId", str)
VocabularyId = NewType("VocabularyId", int)


class ConceptProtocol(Protocol):
    @property
    def id(self) -> ConceptId:
        ...

    @property
    def vocabulary(self) -> VocabularyId:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...


class VocabularyProtocol(Protocol):
    id: VocabularyId
    name: str
    version: str

    def get_concept(self, concept_id: ConceptId) -> ConceptProtocol:
        ...

    @property
    def concepts(self) -> Collection[ConceptProtocol]:
        ...


class DuplicateConceptError(Exception):
    def __init__(self, concept_id: ConceptId, *args: object) -> None:
        super().__init__(f"Concept ID {concept_id} already exists in vocabulary", *args)
        self.concept_id = concept_id


@dataclass(frozen=True)
class VocabularyConcept:
    id: ConceptId
    vocabulary: VocabularyId
    name: str = ""
    description: str = ""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VocabularyConcept):
            return NotImplemented

        return self.id == other.id and self.vocabulary == other.vocabulary


@dataclass(frozen=True)
class LimitedConcept:
    concept: ConceptProtocol
    vocabulary: VocabularyId

    @property
    def base_vocabulary(self) -> VocabularyId:
        return self.concept.vocabulary

    @property
    def id(self) -> ConceptId:
        return self.concept.id

    @property
    def name(self) -> str:
        return self.concept.name

    @property
    def description(self) -> str:
        return self.concept.description

    def __eq__(self, value: object) -> bool:
        base_equal = self.concept == value
        if not base_equal and isinstance(value, LimitedConcept):
            base_equal = self.concept.id == value.id and self.vocabulary == value.vocabulary

        return base_equal


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

    def get_concept(self, concept_id: ConceptId) -> VocabularyConcept:
        index = self._find_concept_index(concept_id)
        return self._concepts[index]

    @property
    def concepts(self) -> Collection[VocabularyConcept]:
        return tuple(self._concepts)

    def add_concept(self, id: ConceptId, name: str = "", description: str = "") -> None:
        if any(c.id == id for c in self._concepts):
            raise DuplicateConceptError(concept_id=id)

        concept = VocabularyConcept(id=id, name=name, description=description, vocabulary=self.id)
        self._concepts.append(concept)

    def _find_concept_index(self, concept_id: ConceptId) -> int:
        for i, concept in enumerate(self._concepts):
            if concept.id == concept_id:
                return i

        raise ValueError(f"Concept ID {concept_id} not found in vocabulary")


UnknownConcept = VocabularyConcept(ConceptId("unknown"), VocabularyId(0))


@dataclass
class LimitedVocabulary:
    id: VocabularyId
    vocabulary: VocabularyProtocol
    name: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        self._disallowed: set[ConceptId] = set()

    @property
    def concepts(self) -> Collection[ConceptProtocol]:
        return [
            LimitedConcept(c, self.id)
            for c in self.vocabulary.concepts
            if c.id not in self._disallowed
        ]

    @property
    def disallowed_concepts(self) -> Collection[ConceptProtocol]:
        return [
            LimitedConcept(c, self.id) for c in self.vocabulary.concepts if c.id in self._disallowed
        ]

    def get_concept(self, concept_id: ConceptId) -> ConceptProtocol:
        if concept_id in self._disallowed:
            raise ValueError(f"Concept {concept_id} is disallowed in this vocabulary")

        return LimitedConcept(self.vocabulary.get_concept(concept_id), self.id)

    def disallow(self, concept_id: ConceptId) -> None:
        self._disallowed.add(concept_id)

    def allow(self, concept_id: ConceptId) -> None:
        self._disallowed.discard(concept_id)

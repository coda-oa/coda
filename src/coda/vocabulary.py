from collections.abc import Collection
from dataclasses import dataclass
from typing import NewType

ConceptId = NewType("ConceptId", str)
VocabularyId = NewType("VocabularyId", int)


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
    is_allowed: bool = True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VocabularyConcept):
            return NotImplemented

        return self.id == other.id and self.vocabulary == other.vocabulary


@dataclass
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

    def allowed_concepts(self) -> Collection[VocabularyConcept]:
        return tuple(c for c in self._concepts if c.is_allowed)

    def is_allowed(self, concept_id: ConceptId) -> bool:
        return any(c.id == concept_id for c in self.allowed_concepts())

    def set_forbidden(self, concept_id: ConceptId) -> None:
        self._replace_allowed(concept_id, is_allowed=False)

    def set_allowed(self, concept_id: ConceptId) -> None:
        self._replace_allowed(concept_id, is_allowed=True)

    def add_concept(
        self, id: ConceptId, name: str = "", description: str = "", *, is_allowed: bool = True
    ) -> None:
        if any(c.id == id for c in self._concepts):
            raise DuplicateConceptError(concept_id=id)

        concept = VocabularyConcept(
            id=id,
            name=name,
            description=description,
            vocabulary=self.id,
            is_allowed=is_allowed,
        )
        self._concepts.append(concept)

    def _replace_allowed(self, concept_id: ConceptId, *, is_allowed: bool) -> None:
        index = self._find_concept_index(concept_id)
        concept = self._concepts[index]
        new_concept = VocabularyConcept(
            concept.id,
            concept.vocabulary,
            concept.name,
            concept.description,
            is_allowed=is_allowed,
        )
        self._concepts[index] = new_concept

    def _find_concept_index(self, concept_id: ConceptId) -> int:
        for i, concept in enumerate(self._concepts):
            if concept.id == concept_id:
                return i

        raise ValueError(f"Concept ID {concept_id} not found in vocabulary")


UnknownConcept = VocabularyConcept(ConceptId("unknown"), VocabularyId(0))

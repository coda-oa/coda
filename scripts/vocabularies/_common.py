import json
from collections.abc import Iterable
from typing import Any, NamedTuple


class Concept(NamedTuple):
    id: str
    name: str
    description: str
    subconcepts: list["Concept"]

    def todict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "subconcepts": [subconcept.todict() for subconcept in self.subconcepts],
        }

    def walk(self) -> Iterable["Concept"]:
        for subconcept in self.subconcepts:
            yield subconcept
            yield from subconcept.walk()


class Vocabulary(NamedTuple):
    name: str
    version: str
    concepts: list[Concept]

    def todict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "concepts": [concept.todict() for concept in self.concepts],
        }

    def walk(self) -> Iterable[Concept]:
        for concept in self.concepts:
            yield concept
            yield from concept.walk()

    def total_concepts(self) -> int:
        return sum(1 for _ in self.walk())


def create_fixture(vocabulary: Vocabulary, vocabulary_pk: int, concept_pk_start: int = 1) -> str:
    voc_dict = {
        "model": "publications.Vocabulary",
        "pk": vocabulary_pk,
        "fields": {
            "name": vocabulary.name,
            "version": vocabulary.version,
        },
    }
    concepts = [
        {
            "model": "publications.Concept",
            "pk": concept_pk,
            "fields": {
                "vocabulary_id": vocabulary_pk,
                "concept_id": concept.id,
                "name": concept.name,
                "hint": concept.description,
            },
        }
        for concept_pk, concept in enumerate(vocabulary.walk(), start=concept_pk_start)
    ]

    fixture = [voc_dict, *concepts]
    return json.dumps(fixture, indent=4)

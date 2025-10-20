import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, NamedTuple, cast
import uuid

import polars as pl


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


class UuidLookup:
    def __init__(self, vocabulary: Vocabulary) -> None:
        self.vocabulary = vocabulary
        self._create_uuid_lookup()
        self._lookup = self._read_uuid_lookup()

    def _create_uuid_lookup(self) -> None:
        _lookup_file = self._lookup_file()
        if not _lookup_file.exists():
            _lookup_file.touch()
            _lookup_file.write_text("concept_id,uuid\n")

    def _lookup_file(self) -> Path:
        lookup_filename = f"{self.vocabulary.name}_{self.vocabulary.version}__uuid_lookup.csv"
        lookup_file = Path(__file__).parent.parent.parent.joinpath("resources", lookup_filename)
        return lookup_file

    def _read_uuid_lookup(self) -> pl.DataFrame:
        _lookup_file = self._lookup_file()
        return pl.read_csv(_lookup_file)

    def get_or_insert(self, concept_id: str) -> str:
        _uuid = self._lookup.filter(pl.col("concept_id") == concept_id).select(pl.col("uuid"))
        if not _uuid.is_empty():
            return cast(str, _uuid["uuid"].cast(dtype=pl.String).first())

        new_uuid = str(uuid.uuid4())
        self._lookup.vstack(
            pl.DataFrame(
                {
                    "concept_id": [concept_id],
                    "uuid": [new_uuid],
                }
            ),
            in_place=True,
        )

        return new_uuid

    def save(self) -> None:
        self._lookup.write_csv(self._lookup_file())


def create_fixture(vocabulary: Vocabulary, vocabulary_pk: int, concept_pk_start: int = 1) -> str:
    uuid_lookup = UuidLookup(vocabulary)
    voc_dict = {
        "model": "publications.Vocabulary",
        "pk": vocabulary_pk,
        "fields": {
            "name": vocabulary.name,
            "version": vocabulary.version,
        },
    }

    concept_with_parents = list(walk_with_parents(vocabulary))
    concept_id_to_pk: dict[str, int] = {}
    concept_entries = []

    for concept_pk, (concept, parent) in enumerate(concept_with_parents, start=concept_pk_start):
        concept_id_to_pk[concept.id] = concept_pk

        concept_entries.append(
            {
                "pk": concept_pk,
                "concept": concept,
                "parent": parent,
                "entity_id": uuid_lookup.get_or_insert(concept.id),
            }
        )

    concept_dicts = []

    for entry in concept_entries:
        concept = cast(Concept, entry["concept"])
        parent = cast(Concept | None, entry["parent"])
        pk = entry["pk"]
        entity_id = entry["entity_id"]

        fields = {
            "vocabulary_id": vocabulary_pk,
            "entity_id": entity_id,
            "concept_id": concept.id,
            "name": concept.name,
            "hint": concept.description,
        }

        if parent:
            parent_pk = concept_id_to_pk.get(parent.id)
            if parent_pk is not None:
                fields["parent"] = parent_pk

        concept_dicts.append(
            {
                "model": "publications.Concept",
                "pk": pk,
                "fields": fields,
            }
        )

    fixture = [voc_dict, *concept_dicts]
    uuid_lookup.save()
    return json.dumps(fixture, indent=4)


def walk_with_parents(vocabulary: Vocabulary) -> Iterable[tuple[Concept, Concept | None]]:
    def _walk(concept: Concept, parent: Concept | None) -> Iterable[tuple[Concept, Concept | None]]:
        yield concept, parent
        for sub in concept.subconcepts:
            yield from _walk(sub, concept)

    for top_level in vocabulary.concepts:
        yield from _walk(top_level, None)

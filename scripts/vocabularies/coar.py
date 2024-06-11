from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any, NamedTuple
from xml.etree import ElementTree

import httpx

COAR_RESOURCE_TYPES_3_1 = (
    "https://vocabularies.coar-repositories.org/resource_types/3.1/resource_types_for_dspace_en.xml"
)


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


def download_vocabulary(url: str) -> bytes:
    response = httpx.get(url)
    response.raise_for_status()
    return response.content


def parse_vocabulary(content: str, name: str, version: str) -> Vocabulary:
    root = ElementTree.fromstring(content)
    root_composed = root.find("isComposedBy")
    if root_composed is None:
        raise ValueError("Invalid vocabulary file")

    concepts = [_parse_concept(concept) for concept in root_composed.findall("node")]
    return Vocabulary(name, version, concepts)


def _parse_concept(element: ElementTree.Element) -> Concept:
    id = element.get("id", "")
    name = element.get("label", "")
    description = element.findtext("hasNote", "")

    composed = element.find("isComposedBy")
    if composed is not None:
        subconcepts = [_parse_concept(subconcept) for subconcept in composed.findall("node")]
    else:
        subconcepts = []

    return Concept(id, name, description, subconcepts)


def export_fixture() -> None:
    content = download_vocabulary(COAR_RESOURCE_TYPES_3_1)
    vocabulary = parse_vocabulary(content.decode(), "COAR Resource Types", "3.1")
    voc_dict = {
        "model": "publications.Vocabulary",
        "pk": 1,
        "fields": {
            "name": vocabulary.name,
            "version": vocabulary.version,
        },
    }
    concepts = [
        {
            "model": "publications.Concept",
            "pk": i + 1,
            "fields": {
                "vocabulary_id": 1,
                "concept_id": concept.id,
                "name": concept.name,
                "hint": concept.description,
            },
        }
        for i, concept in enumerate(vocabulary.walk())
    ]

    fixture = [voc_dict, *concepts]
    fixture_json = json.dumps(fixture, indent=4)
    Path("config/fixtures/coar_resource_types_3_1.json").write_text(fixture_json)


if __name__ == "__main__":
    export_fixture()

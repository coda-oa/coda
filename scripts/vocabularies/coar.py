from xml.etree import ElementTree

import httpx

from scripts.vocabularies._common import Concept, Vocabulary

COAR_RESOURCE_TYPES_3_1 = (
    "https://vocabularies.coar-repositories.org/resource_types/3.1/resource_types_for_dspace_en.xml"
)


def download_vocabulary(url: str) -> bytes:
    response = httpx.get(url)
    response.raise_for_status()
    return response.content


def parse_vocabulary() -> Vocabulary:
    content = download_vocabulary(COAR_RESOURCE_TYPES_3_1)
    return _parse_vocabulary(content.decode(), "COAR Resource Types", "3.1")


def _parse_vocabulary(content: str, name: str, version: str) -> Vocabulary:
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

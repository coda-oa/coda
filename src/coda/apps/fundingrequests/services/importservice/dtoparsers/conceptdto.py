from coda.apps.publications.dto import ConceptDto
from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.vocabulary import UnknownConcept

from ..dto import ConceptImportDto


def parse_dto(import_dto: ConceptImportDto) -> ConceptDto:
    if not import_dto.name:
        return ConceptDto.from_concept(UnknownConcept)

    vocabulary = vocabulary_repository.newest_base_vocabulary_by_name(import_dto.vocabulary_name)
    for concept in vocabulary.concepts:
        if concept.name == import_dto.name:
            return ConceptDto.from_concept(concept)

    raise ValueError(
        f"Concept {import_dto.name} not found in vocabulary {import_dto.vocabulary_name}"
    )

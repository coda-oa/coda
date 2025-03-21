import pydantic

from coda.apps.publications.repositories import vocabulary_repository
from coda.vocabulary import VocabularyConcept


class ConceptImportDto(pydantic.BaseModel):
    name: str
    vocabulary_name: str

    def parse(self) -> VocabularyConcept:
        vocabulary = vocabulary_repository.newest_base_vocabulary_by_name(self.vocabulary_name)
        for concept in vocabulary.concepts:
            if concept.name == self.name:
                return concept

        raise ValueError(f"Concept {self.name} not found in vocabulary {self.vocabulary_name}")

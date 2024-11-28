from coda.apps.publications.repositories import vocabulary_repository
from coda.vocabulary import VocabularyId


def create_limited_from(vocabulary_id: VocabularyId, name: str) -> VocabularyId:
    vocabulary = vocabulary_repository.create_limited(base_vocabulary_id=vocabulary_id, name=name)
    return vocabulary.id


def disallow_concept(vocabulary_id: VocabularyId, concept_id: str) -> None:
    limited = vocabulary_repository.get_limited_by_id(vocabulary_id)
    limited.disallow(concept_id)
    vocabulary_repository.save(limited)


def allow_concept(vocabulary_id: VocabularyId, concept_id: str) -> None:
    limited = vocabulary_repository.get_limited_by_id(vocabulary_id)
    limited.allow(concept_id)
    vocabulary_repository.save(limited)

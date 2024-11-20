import pytest

from coda.apps.publications.repositories import vocabulary_repository
from coda.vocabulary import ConceptId, LimitedVocabulary, Vocabulary, VocabularyId


@pytest.mark.django_db
def test__saved_limited_vocabulary__get_by_id__returns_limited_vocabulary() -> None:
    v = Vocabulary(id=VocabularyId(999), name="test", version="1.0")
    v.add_concept(ConceptId("allowed"))
    v.add_concept(ConceptId("forbidden"))
    vocabulary_repository.save(v)

    limited_vocabulary = LimitedVocabulary(id=VocabularyId(1000), vocabulary=v)
    limited_vocabulary.disallow(ConceptId("forbidden"))

    vocabulary_repository.save(limited_vocabulary)

    result = vocabulary_repository.get_by_id(VocabularyId(1000))

    assert isinstance(result, LimitedVocabulary)
    assert list(result.concepts) == [v.get_concept(ConceptId("allowed"))]
    assert list(result.disallowed_concepts) == [v.get_concept(ConceptId("forbidden"))]

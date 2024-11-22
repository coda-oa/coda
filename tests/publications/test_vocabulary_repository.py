import pytest

from coda.apps.publications.repositories import vocabulary_repository
from coda.vocabulary import ConceptId, LimitedVocabulary


@pytest.mark.django_db
def test__saved_limited_vocabulary__get_by_id__returns_limited_vocabulary() -> None:
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept(ConceptId("allowed"))
    v.add_concept(ConceptId("forbidden"))
    vocabulary_repository.save(v)

    limited_vocabulary = vocabulary_repository.create_limited(v.id, name="limited")
    limited_vocabulary.disallow(ConceptId("forbidden"))
    vocabulary_repository.save(limited_vocabulary)

    actual = vocabulary_repository.get_by_id(limited_vocabulary.id)
    assert isinstance(actual, LimitedVocabulary)
    assert list(actual.concepts) == [v.get_concept(ConceptId("allowed"))]
    assert list(actual.disallowed_concepts) == [v.get_concept(ConceptId("forbidden"))]


@pytest.mark.django_db
def test__saved_limited_vocabulary__allowing_previously_forbidden_concept__saves_only_disallowed_concepts() -> (
    None
):
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept(ConceptId("allowed"))
    v.add_concept(ConceptId("forbidden"))
    vocabulary_repository.save(v)

    limited_vocabulary = vocabulary_repository.create_limited(v.id, name="limited")
    limited_vocabulary.disallow(ConceptId("forbidden"))
    vocabulary_repository.save(limited_vocabulary)

    limited_vocabulary = vocabulary_repository.get_limited_by_id(limited_vocabulary.id)
    limited_vocabulary.allow(ConceptId("forbidden"))
    vocabulary_repository.save(limited_vocabulary)

    result = vocabulary_repository.get_by_id(limited_vocabulary.id)
    assert set(result.concepts) == set(v.concepts)

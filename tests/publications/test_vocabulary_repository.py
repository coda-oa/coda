from collections.abc import Collection
import pytest

from coda.apps.publications.repositories import vocabulary_repository
from coda.vocabulary import LimitedVocabulary, VocabularyConcept


@pytest.mark.django_db
def test__saved_limited_vocabulary__get_by_id__returns_limited_vocabulary() -> None:
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept("allowed")
    v.add_concept("forbidden")
    vocabulary_repository.save(v)

    limited_vocabulary = vocabulary_repository.create_limited(v.id, name="limited")
    limited_vocabulary.disallow("forbidden")
    vocabulary_repository.save(limited_vocabulary)

    actual = vocabulary_repository.get_by_id(limited_vocabulary.id)
    assert isinstance(actual, LimitedVocabulary)
    assert list(actual.concepts) == [v.get_concept("allowed")]
    assert list(actual.disallowed_concepts) == [v.get_concept("forbidden")]


@pytest.mark.django_db
def test__saved_limited_vocabulary__allowing_previously_forbidden_concept__saves_only_disallowed_concepts() -> (
    None
):
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept("allowed")
    v.add_concept("forbidden")
    vocabulary_repository.save(v)

    limited_vocabulary = vocabulary_repository.create_limited(v.id, name="limited")
    limited_vocabulary.disallow("forbidden")
    vocabulary_repository.save(limited_vocabulary)

    limited_vocabulary = vocabulary_repository.get_limited_by_id(limited_vocabulary.id)
    limited_vocabulary.allow("forbidden")
    vocabulary_repository.save(limited_vocabulary)

    result = vocabulary_repository.get_by_id(limited_vocabulary.id)
    assert sorted_by_concept_id(result.concepts) == sorted_by_concept_id(v.concepts)


def sorted_by_concept_id(concepts: Collection[VocabularyConcept]) -> list[VocabularyConcept]:
    return sorted(concepts, key=lambda c: c.concept_id)

import pytest

from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publications.services import vocabularies
from coda.vocabulary import ConceptId, LimitedVocabulary, Vocabulary, VocabularyId


@pytest.mark.django_db
def test__can_create_limited_vocabulary_from_vocabulary() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept(id=ConceptId("test-concept"), name="", description="")
    vocabulary_repository.save(vocabulary)

    vid = vocabularies.create_limited_from(vocabulary.id, "limited")

    actual = vocabulary_repository.get_by_id(vid)
    assert isinstance(actual, LimitedVocabulary)
    assert actual.name == "limited"
    assert actual.vocabulary.id == vocabulary.id
    assert actual.version == actual.vocabulary.version


@pytest.mark.django_db
def test__limited_vocabulary__disallowing_concept__is_saved_to_database() -> None:
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(id=ConceptId("test-concept"), name="", description="")
    vocabulary_repository.save(vocabulary)

    vid = vocabularies.create_limited_from(vocabulary.id, "limited")

    vocabularies.disallow_concept(vid, ConceptId("test-concept"))

    actual = vocabulary_repository.get_limited_by_id(vid)
    assert list(actual.disallowed_concepts) == [vocabulary.get_concept(ConceptId("test-concept"))]


@pytest.mark.django_db
def test__limited_vocabulary_with_disallowed_concepts__allowing_concept__is_saved_to_database() -> (
    None
):
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(id=ConceptId("test-concept"), name="", description="")
    vocabulary_repository.save(vocabulary)

    vid = vocabularies.create_limited_from(vocabulary.id, "limited")
    vocabularies.disallow_concept(vid, ConceptId("test-concept"))

    vocabularies.allow_concept(vid, ConceptId("test-concept"))

    actual = vocabulary_repository.get_limited_by_id(vid)
    assert list(actual.disallowed_concepts) == []

import pytest

from coda.vocabulary import LimitedVocabulary, Vocabulary, VocabularyId


def test__limited_vocabulary__all_concepts_are_allowed_by_default() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept")

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)

    list(sut.concepts) == list(vocabulary.concepts)


def test__limited_vocabulary__all_concepts_belong_to_limited_vocabulary() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept")
    vocabulary.add_concept(concept_id="another-concept")

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)

    assert {concept.vocabulary for concept in sut.concepts} == {VocabularyId(1)}


def test__set_concept_forbidden__concept_is_not_in_concepts() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    assert list(sut.concepts) == []


def test__two_concepts__one_disallowed__concepts_contains_allowed() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    allowed_id = "test-concept"
    forbidden_id = "test-concept-2"
    vocabulary.add_concept(allowed_id)
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    assert list(sut.concepts) == [vocabulary.get_concept(allowed_id)]


def test__disallowed_concept__belongs_to_limited_vocabulary() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    assert {c.vocabulary for c in sut.disallowed_concepts} == {VocabularyId(1)}


def test__three_concepts__two_disallowed__concepts_contains_allowed() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    allowed_id = "test-concept"
    forbidden_id = "test-concept-2"
    forbidden_id_2 = "test-concept-3"
    vocabulary.add_concept(allowed_id)
    vocabulary.add_concept(forbidden_id)
    vocabulary.add_concept(forbidden_id_2)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id)
    sut.disallow(forbidden_id_2)

    assert list(sut.concepts) == [vocabulary.get_concept(allowed_id)]


def test__multiple_disallowed__all_contained_in_disallowed_concepts() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id_1 = "test-concept"
    forbidden_id_2 = "test-concept-2"
    forbidden_id_3 = "test-concept-3"
    vocabulary.add_concept(forbidden_id_1)
    vocabulary.add_concept(forbidden_id_2)
    vocabulary.add_concept(forbidden_id_3)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id_1)
    sut.disallow(forbidden_id_2)
    sut.disallow(forbidden_id_3)

    assert list(sut.disallowed_concepts) == [
        vocabulary.get_concept(forbidden_id_1),
        vocabulary.get_concept(forbidden_id_2),
        vocabulary.get_concept(forbidden_id_3),
    ]


def test__get_concept__returns_limited_concept() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    concept_id = "test-concept"
    vocabulary.add_concept(concept_id)

    limited_id = VocabularyId(1)
    sut = LimitedVocabulary(id=limited_id, vocabulary=vocabulary)

    assert sut.get_concept(concept_id) == vocabulary.get_concept(concept_id)
    assert sut.get_concept(concept_id).vocabulary == limited_id


def test__disallowed_concept__get_concept__raises_error() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    with pytest.raises(ValueError):
        sut.get_concept(forbidden_id)


def test__disallowed_concepts__allowing__concept_is_in_concepts() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), vocabulary=vocabulary)
    sut.disallow(forbidden_id)
    sut.allow(forbidden_id)

    assert list(sut.concepts) == [vocabulary.get_concept(forbidden_id)]
    assert sut.get_concept(forbidden_id) == vocabulary.get_concept(forbidden_id)
    assert list(sut.disallowed_concepts) == []

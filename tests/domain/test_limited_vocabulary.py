import pytest

from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
)


def test__limited_vocabulary__all_concepts_are_allowed_by_default() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept")

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)

    assert list(sut.concepts) == list(vocabulary.concepts)


def test__limited_vocabulary__all_concepts_belong_to_limited_vocabulary() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept")
    vocabulary.add_concept(concept_id="another-concept")

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)

    assert {concept.vocabulary for concept in sut.concepts} == {VocabularyId(1)}


def test__set_concept_forbidden__concept_is_not_in_concepts() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    assert list(sut.concepts) == []


def test__two_concepts__one_disallowed__concepts_contains_allowed() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    allowed_id = "test-concept"
    forbidden_id = "test-concept-2"
    vocabulary.add_concept(allowed_id)
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    assert list(sut.concepts) == [vocabulary.get_concept(allowed_id)]


def test__disallowed_concept__belongs_to_limited_vocabulary() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
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

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
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

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
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
    sut = LimitedVocabulary(id=limited_id, base_vocabulary=vocabulary)

    assert sut.get_concept(concept_id) == vocabulary.get_concept(concept_id)
    assert sut.get_concept(concept_id).vocabulary == limited_id


def test__disallowed_concept__get_concept__raises_error() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
    sut.disallow(forbidden_id)

    with pytest.raises(ValueError):
        sut.get_concept(forbidden_id)


def test__disallowed_concepts__allowing__concept_is_in_concepts() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_id = "test-concept"
    vocabulary.add_concept(forbidden_id)

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
    sut.disallow(forbidden_id)
    sut.allow(forbidden_id)

    assert list(sut.concepts) == [vocabulary.get_concept(forbidden_id)]
    assert sut.get_concept(forbidden_id) == vocabulary.get_concept(forbidden_id)
    assert list(sut.disallowed_concepts) == []


def test__limited_vocabulary__get_concepts_hierarchy__concepts_belong_to_limited_vocabulary() -> (
    None
):
    vocabulary = Vocabulary(id=VocabularyId(0), name="base", version="1.0")
    vocabulary.add_concept(concept_id="root-concept", name="Root")
    vocabulary.add_concept(concept_id="child-concept", name="Child")

    limited_vocab_id = VocabularyId(1)
    sut = LimitedVocabulary(id=limited_vocab_id, base_vocabulary=vocabulary)

    roots, children_map = sut.get_concept_hierarchy()

    assert_concepts_belong_to_vocabulary(limited_vocab_id, roots)
    assert_child_concepts_belong_to_vocabulary(limited_vocab_id, children_map)


def assert_concepts_belong_to_vocabulary(
    limited_vocab_id: VocabularyId, roots: list[VocabularyConcept]
) -> None:
    for concept in roots:
        assert concept.vocabulary == limited_vocab_id


def assert_child_concepts_belong_to_vocabulary(
    limited_vocab_id: VocabularyId, children_map: dict[ConceptId, list[VocabularyConcept]]
) -> None:
    for children in children_map.values():
        for concept in children:
            assert concept.vocabulary == limited_vocab_id


def test__single_level_limited_vocab__get_root_base_vocabulary__returns_original_base_vocabulary() -> (
    None
):
    base_vocab = Vocabulary(id=VocabularyId(0), name="Base", version="1.0")
    base_vocab.add_concept(concept_id="concept-a")

    limited_vocab = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=base_vocab)

    root = limited_vocab.get_root_base_vocabulary()

    assert root == base_vocab


def test__multiple_nested_limited_vocabularies__get_root_base_vocabulary__returns_original_base_vocabulary() -> (
    None
):
    base_vocab = Vocabulary(id=VocabularyId(0), name="Base", version="1.0")
    base_vocab.add_concept(concept_id="concept-a")
    base_vocab.add_concept(concept_id="concept-b")

    limited1 = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=base_vocab)
    limited1.disallow("concept-a")

    limited2 = LimitedVocabulary(id=VocabularyId(2), base_vocabulary=limited1)

    limited3 = LimitedVocabulary(id=VocabularyId(3), base_vocabulary=limited2)

    root = limited3.get_root_base_vocabulary()

    assert root == base_vocab
    assert root.id == VocabularyId(0)

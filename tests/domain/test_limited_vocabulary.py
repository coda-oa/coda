import pytest

from coda.domain.vocabulary import (
    ConceptId,
    ConceptNotAllowedError,
    ConceptNotFoundError,
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

    with pytest.raises(ConceptNotAllowedError):
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


def test__disallowed_concept__get_concept_by_id__raises_concept_not_allowed_error() -> None:
    """get_concept_by_id must raise ConceptNotAllowedError when the concept's string ID
    is in the disallow list, even though _disallowed holds str values and `id` is a UUID."""
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    forbidden_concept_id = "journal-article"
    vocabulary.add_concept(forbidden_concept_id)

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)
    sut.disallow(forbidden_concept_id)

    # Retrieve the UUID of the disallowed concept from the base vocabulary
    concept_uuid = vocabulary.get_concept(forbidden_concept_id).id

    with pytest.raises(ConceptNotAllowedError):
        sut.get_concept_by_id(concept_uuid)


def test__is_concept_allowed__nonexistent_concept__returns_false() -> None:
    """is_concept_allowed must return False for concept IDs that do not exist in the
    base vocabulary, even if they are not on the disallow list."""
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept("real-concept")

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)

    # "ghost-concept" is not disallowed and not in base vocab — should be False
    assert not sut.is_concept_allowed("ghost-concept")


def test__get_concept_by_id__uuid_not_in_base_vocabulary__raises_concept_not_found_error() -> None:
    """get_concept_by_id must propagate ConceptNotFoundError when the UUID does not
    exist in the base vocabulary at all."""
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept("existing-concept")

    sut = LimitedVocabulary(id=VocabularyId(1), base_vocabulary=vocabulary)

    # A freshly-generated ConceptId that was never added to the vocabulary
    nonexistent_id = ConceptId.new()

    with pytest.raises(ConceptNotFoundError):
        sut.get_concept_by_id(nonexistent_id)

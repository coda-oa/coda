import pytest

from coda.domain.vocabulary import (
    ConceptId,
    DuplicateConceptError,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
)


def assert_all_concepts_fields_eq(
    concepts: list[VocabularyConcept], other_concepts: list[VocabularyConcept]
) -> None:
    for concept, other_concept in zip(concepts, other_concepts):
        assert_concept_fields_eq(concept, other_concept)


def assert_concept_fields_eq(concept: VocabularyConcept, other_concept: VocabularyConcept) -> bool:
    assert concept.concept_id == other_concept.concept_id
    assert concept.name == other_concept.name
    assert concept.description == other_concept.description
    assert concept.vocabulary == other_concept.vocabulary
    return True


DUMMY_CONCEPT_ID = ConceptId.new()


def test__can_create_vocabulary_with_concepts() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    sut.add_concept(concept_id="test-concept", name="Test Concept", description="A test concept")
    sut.add_concept(concept_id="test-concept-2", name="Test Concept", description="A test concept")

    expected_concepts = [
        VocabularyConcept(
            id=DUMMY_CONCEPT_ID,
            concept_id="test-concept",
            name="Test Concept",
            description="A test concept",
            vocabulary=VocabularyId(0),
        ),
        VocabularyConcept(
            id=DUMMY_CONCEPT_ID,
            concept_id="test-concept-2",
            name="Test Concept",
            description="A test concept",
            vocabulary=VocabularyId(0),
        ),
    ]

    assert_all_concepts_fields_eq(list(sut.concepts), expected_concepts)


def test__concept_ids__must_be_unique() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    sut.add_concept(concept_id="test-concept", name="Test Concept", description="A test concept")

    with pytest.raises(DuplicateConceptError):
        sut.add_concept(
            concept_id="test-concept", name="Test Concept", description="A test concept"
        )


def test__two_concepts_with_same_id__are_always_equal() -> None:
    vid = VocabularyId(0)
    concept = VocabularyConcept(id=DUMMY_CONCEPT_ID, concept_id="test-concept", vocabulary=vid)
    same_concept_with_more_data = VocabularyConcept(
        id=DUMMY_CONCEPT_ID, concept_id="same-concept", vocabulary=vid, name="Additional Info"
    )

    assert concept == same_concept_with_more_data
